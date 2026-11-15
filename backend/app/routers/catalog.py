import io
from time import perf_counter

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from ..config import CURRENCY, MAX_UPLOAD_BYTES, STRIPE_SECRET_KEY
from ..db import get_conn
from ..embedder import embed_image, to_pgvector
from ..security import optional_user
from ..services import PRODUCT_COLUMNS, product_json

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/config")
def config():
    return {"currency": CURRENCY.upper(), "stripe_enabled": bool(STRIPE_SECRET_KEY)}


@router.get("/categories")
def categories(conn=Depends(get_conn)):
    return conn.execute(
        """SELECT c.id, c.name, c.slug, COUNT(p.id) FILTER (WHERE p.is_active) AS product_count
           FROM categories c LEFT JOIN products p ON p.category_id = c.id
           GROUP BY c.id ORDER BY c.name"""
    ).fetchall()


@router.get("/products")
def list_products(category_id: int | None = None, q: str | None = None,
                  limit: int = 60, offset: int = 0, conn=Depends(get_conn)):
    rows = conn.execute(
        f"""SELECT {PRODUCT_COLUMNS}
            FROM products p JOIN categories c ON c.id = p.category_id
            WHERE p.is_active
              AND (%(cat)s::int IS NULL OR p.category_id = %(cat)s::int)
              AND (%(q)s::text IS NULL OR lower(p.name) LIKE '%%' || lower(%(q)s::text) || '%%')
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT %(limit)s OFFSET %(offset)s""",
        {"cat": category_id, "q": q or None, "limit": min(limit, 100), "offset": offset},
    ).fetchall()
    return [product_json(r) for r in rows]


@router.get("/products/{product_id}")
def get_product(product_id: int, conn=Depends(get_conn)):
    row = conn.execute(
        f"""SELECT {PRODUCT_COLUMNS}
            FROM products p JOIN categories c ON c.id = p.category_id
            WHERE p.id = %s AND p.is_active""", (product_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Product not found.")
    return product_json(row)


# Heuristic: CLIP image-to-image cosine similarity is rarely below ~0.45 for clothing photos,
# and ~0.97+ means "practically the same picture". Rescale that range to 0-100 for display.
def match_percent(similarity: float) -> int:
    return round(max(0.0, min(1.0, (similarity - 0.45) / (0.97 - 0.45))) * 100)


@router.get("/products/{product_id}/similar")
def similar_products(product_id: int, limit: int = 6, conn=Depends(get_conn)):
    """'More like this' - uses the vector already stored in the DB, so no model call is needed."""
    rows = conn.execute(
        f"""SELECT {PRODUCT_COLUMNS},
                   1 - (e.embedding <=> (SELECT embedding FROM product_embeddings WHERE product_id = %(id)s)) AS similarity
            FROM product_embeddings e
            JOIN products p   ON p.id = e.product_id
            JOIN categories c ON c.id = p.category_id
            WHERE p.is_active AND p.id <> %(id)s
            ORDER BY e.embedding <=> (SELECT embedding FROM product_embeddings WHERE product_id = %(id)s)
            LIMIT %(limit)s""",
        {"id": product_id, "limit": min(limit, 24)},
    ).fetchall()
    out = []
    for r in rows:
        r = product_json(r)
        r["similarity"] = float(r["similarity"])
        r["match_percent"] = match_percent(r["similarity"])
        out.append(r)
    return out


@router.post("/search")
def visual_search(file: UploadFile = File(...), category_id: int | None = Form(None),
                  limit: int = Form(12), conn=Depends(get_conn), user=Depends(optional_user)):
    t0 = perf_counter()
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image is larger than 8 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "That file isn't an image we can read. Try a JPG or PNG.")

    vec = to_pgvector(embed_image(img))                       # 1) image -> vector
    rows = conn.execute(                                      # 2) nearest neighbours by cosine distance
        f"""SELECT {PRODUCT_COLUMNS},
                   1 - (e.embedding <=> %(vec)s::vector) AS similarity
            FROM product_embeddings e
            JOIN products p   ON p.id = e.product_id
            JOIN categories c ON c.id = p.category_id
            WHERE p.is_active
              AND (%(cat)s::int IS NULL OR p.category_id = %(cat)s::int)
            ORDER BY e.embedding <=> %(vec)s::vector
            LIMIT %(limit)s""",
        {"vec": vec, "cat": category_id, "limit": max(1, min(limit, 48))},
    ).fetchall()

    results = []
    for r in rows:
        r = product_json(r)
        r["similarity"] = round(float(r["similarity"]), 4)
        r["match_percent"] = match_percent(r["similarity"])
        results.append(r)

    latency = round((perf_counter() - t0) * 1000)
    conn.execute(
        "INSERT INTO search_logs (user_id, top_product_id, top_similarity, latency_ms) VALUES (%s, %s, %s, %s)",
        (user["id"] if user else None, results[0]["id"] if results else None,
         results[0]["similarity"] if results else None, latency),
    )
    conn.commit()
    return {"results": results, "latency_ms": latency}
