"""Catalog operations shared by the admin API and the seed script."""
import uuid

from PIL import Image

from .config import PRODUCT_DIR
from .embedder import MODEL_NAME, embed_image, to_pgvector


def save_product_image(img: Image.Image) -> str:
    """Store a normalised JPEG and return the path relative to /media."""
    img = img.convert("RGB")
    img.thumbnail((1024, 1024))
    name = f"{uuid.uuid4().hex}.jpg"
    img.save(PRODUCT_DIR / name, "JPEG", quality=88)
    return f"products/{name}"


def save_embedding(conn, product_id: int, vec: list[float]) -> None:
    conn.execute(
        """INSERT INTO product_embeddings (product_id, embedding, model_name)
           VALUES (%s, %s::vector, %s)
           ON CONFLICT (product_id)
           DO UPDATE SET embedding = EXCLUDED.embedding, model_name = EXCLUDED.model_name,
                         created_at = now()""",
        (product_id, to_pgvector(vec), MODEL_NAME),
    )


def create_product(conn, *, name, description, price_cents, stock, category_id, img: Image.Image,
                   vec: list[float] | None = None) -> int:
    """Insert product + image + embedding in ONE transaction (all or nothing)."""
    path = save_product_image(img)
    row = conn.execute(
        """INSERT INTO products (category_id, name, description, price_cents, stock, image_path)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (category_id, name, description, price_cents, stock, path),
    ).fetchone()
    save_embedding(conn, row["id"], vec if vec is not None else embed_image(img))
    return row["id"]


def product_json(row: dict) -> dict:
    out = dict(row)
    out["image_url"] = f"/media/{out.pop('image_path')}"
    return out


PRODUCT_COLUMNS = """p.id, p.name, p.description, p.price_cents, p.stock, p.image_path,
                     p.category_id, c.name AS category"""
