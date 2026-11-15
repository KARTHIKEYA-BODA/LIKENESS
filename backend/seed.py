"""Fill the database with demo users, categories and ~48 generated products.

    python seed.py            # add demo data (skips if products already exist)
    python seed.py --reset    # wipe catalog/orders first
"""
import random
import sys

from app.db import pool
from app.embedder import embed_images
from app.security import hash_password
from app.services import create_product
from app.synth import CATEGORY, NOUNS, PALETTE, PATTERNS, SILHOUETTES, make_garment

RESET = "--reset" in sys.argv


def main():
    pool.open()
    with pool.connection() as conn:
        if RESET:
            conn.execute("TRUNCATE order_items, orders, cart_items, carts, product_embeddings, "
                         "search_logs, products, categories RESTART IDENTITY CASCADE")
        elif conn.execute("SELECT 1 FROM products LIMIT 1").fetchone():
            print("Products already exist. Run with --reset to start over.")
            return

        for email, pw, name, role in [("admin@likeness.dev", "admin123", "Store Admin", "admin"),
                                      ("shopper@likeness.dev", "shopper123", "Demo Shopper", "customer")]:
            conn.execute("""INSERT INTO users (email, password_hash, full_name, role) VALUES (%s,%s,%s,%s)
                            ON CONFLICT DO NOTHING""", (email, hash_password(pw), name, role))

        cat_ids = {}
        for name in sorted(set(CATEGORY.values())):
            row = conn.execute("""INSERT INTO categories (name, slug) VALUES (%s, %s)
                                  ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
                               (name, name.lower())).fetchone()
            cat_ids[name] = row["id"]

        rng = random.Random(42)
        specs = []
        for kind in SILHOUETTES:
            combos = [(c, p) for c in PALETTE for p in PATTERNS]
            rng.shuffle(combos)
            for color, pattern in combos[:12]:
                specs.append((kind, color, pattern))

        print(f"Generating {len(specs)} product photos...")
        images = [make_garment(k, c, p, seed=i) for i, (k, c, p) in enumerate(specs)]
        print("Computing CLIP embeddings (first run downloads the model, ~600 MB)...")
        vectors = []
        for i in range(0, len(images), 16):
            vectors += embed_images(images[i:i + 16])

        for (kind, color, pattern), img, vec in zip(specs, images, vectors):
            noun = rng.choice(NOUNS[kind])
            label = noun if pattern == "Solid" else f"{pattern} {noun}"
            create_product(
                conn, name=f"{color} {label}",
                description=f"A {pattern.lower()} {color.lower()} {noun.lower()} in soft, breathable fabric.",
                price_cents=rng.randrange(1900, 12900, 100) + 99, stock=rng.choice([0, 3, 5, 8, 12, 20, 25]),
                category_id=cat_ids[CATEGORY[kind]], img=img, vec=vec,
            )
        conn.commit()
    print("Done.  Admin: admin@likeness.dev / admin123   Shopper: shopper@likeness.dev / shopper123")


if __name__ == "__main__":
    main()
