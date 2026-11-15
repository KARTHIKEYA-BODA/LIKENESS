import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from ..config import MAX_UPLOAD_BYTES
from ..db import get_conn
from ..embedder import embed_images
from ..security import require_admin
from ..services import create_product, product_json, save_embedding

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats")
def stats(conn=Depends(get_conn)):
    totals = conn.execute(
        """SELECT
             (SELECT COALESCE(SUM(total_cents),0) FROM orders WHERE status IN ('paid','shipped')) AS revenue_cents,
             (SELECT COUNT(*) FROM orders WHERE status IN ('paid','shipped'))                      AS orders,
             (SELECT COUNT(*) FROM products WHERE is_active)                                       AS products,
             (SELECT COUNT(*) FROM users WHERE role = 'customer')                                  AS customers,
             (SELECT COUNT(*) FROM search_logs)                                                    AS searches,
             (SELECT COALESCE(ROUND(AVG(latency_ms)),0) FROM search_logs)                          AS avg_latency_ms"""
    ).fetchone()
    best = conn.execute(
        "SELECT id, name, units_sold, revenue_cents FROM v_product_sales WHERE units_sold > 0 ORDER BY revenue_cents DESC LIMIT 5"
    ).fetchall()
    low = conn.execute(
        "SELECT id, name, stock FROM products WHERE is_active AND stock <= 5 ORDER BY stock, name LIMIT 8"
    ).fetchall()
    top_matched = conn.execute(
        """SELECT p.id, p.name, COUNT(*) AS times_top_match
           FROM search_logs s JOIN products p ON p.id = s.top_product_id
           GROUP BY p.id, p.name ORDER BY times_top_match DESC LIMIT 5"""
    ).fetchall()
    return {"totals": totals, "best_sellers": best, "low_stock": low, "top_matched": top_matched}


@router.get("/products")
def all_products(conn=Depends(get_conn)):
    rows = conn.execute(
        """SELECT p.id, p.name, p.description, p.price_cents, p.stock, p.image_path, p.is_active,
                  p.category_id, c.name AS category, (e.product_id IS NOT NULL) AS indexed
           FROM products p JOIN categories c ON c.id = p.category_id
           LEFT JOIN product_embeddings e ON e.product_id = p.id
           ORDER BY p.id DESC"""
    ).fetchall()
    return [product_json(r) for r in rows]


@router.get("/orders")
def all_orders(conn=Depends(get_conn)):
    return conn.execute(
        """SELECT o.id, o.status, o.total_cents, o.created_at, u.email
           FROM orders o JOIN users u ON u.id = o.user_id ORDER BY o.created_at DESC LIMIT 50"""
    ).fetchall()


@router.post("/products")
def add_product(name: str = Form(...), description: str = Form(""), price: float = Form(...),
                stock: int = Form(0), category_id: int = Form(...), image: UploadFile = File(...),
                conn=Depends(get_conn)):
    data = image.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image is larger than 8 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "That file isn't a readable image.")
    if price < 0 or stock < 0:
        raise HTTPException(422, "Price and stock can't be negative.")
    pid = create_product(conn, name=name.strip(), description=description.strip(),
                         price_cents=round(price * 100), stock=stock, category_id=category_id, img=img)
    conn.commit()
    return {"id": pid}


class ProductPatch(BaseModel):
    name: str | None = None
    price: float | None = None
    stock: int | None = None
    is_active: bool | None = None


@router.patch("/products/{product_id}")
def patch_product(product_id: int, body: ProductPatch, conn=Depends(get_conn)):
    sets, params = [], {"id": product_id}
    if body.name is not None:
        sets.append("name = %(name)s"); params["name"] = body.name
    if body.price is not None:
        sets.append("price_cents = %(price)s"); params["price"] = round(body.price * 100)
    if body.stock is not None:
        sets.append("stock = %(stock)s"); params["stock"] = body.stock
    if body.is_active is not None:
        sets.append("is_active = %(active)s"); params["active"] = body.is_active
    if not sets:
        raise HTTPException(400, "Nothing to update.")
    row = conn.execute(f"UPDATE products SET {', '.join(sets)} WHERE id = %(id)s RETURNING id", params).fetchone()
    if not row:
        raise HTTPException(404, "Product not found.")
    conn.commit()
    return {"id": product_id}


@router.post("/reindex")
def reindex(conn=Depends(get_conn)):
    """Re-embed every product image (e.g. after switching to a different vision model)."""
    from ..config import UPLOAD_DIR
    rows = conn.execute("SELECT id, image_path FROM products").fetchall()
    done = 0
    for i in range(0, len(rows), 16):
        chunk = rows[i:i + 16]
        imgs = [Image.open(UPLOAD_DIR / r["image_path"]) for r in chunk]
        for r, vec in zip(chunk, embed_images(imgs)):
            save_embedding(conn, r["id"], vec)
            done += 1
    conn.commit()
    return {"reindexed": done}
