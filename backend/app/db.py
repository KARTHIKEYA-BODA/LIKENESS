import logging
from pathlib import Path
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL, validate_settings

logger = logging.getLogger("uvicorn")

# A small pool of reusable connections. Rows come back as plain dicts.
pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10,
                      kwargs={"row_factory": dict_row}, open=False)


def get_conn():
    """FastAPI dependency that returns a pooled Postgres connection."""
    with pool.connection() as conn:
        yield conn


def check_connection() -> None:
    """Verify the configured Supabase/Postgres database before accepting requests."""
    validate_settings()
    with pool.connection() as conn:
        conn.execute("SELECT 1").fetchone()


def init_db() -> None:
    """Automatically initialize tables and seed data if the database is fresh."""
    validate_settings()
    with pool.connection() as conn:
        # 1. Try enabling pgvector extension
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
        except Exception as e:
            logger.warning(f"pgvector extension notice: {e}")
            conn.rollback()

        # 2. Check if tables exist
        row = conn.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'users'
            );
        """).fetchone()

        if not row or not row.get("exists"):
            logger.info("Initializing database schema...")
            schema_file = Path(__file__).resolve().parent / "schema.sql"
            if schema_file.exists():
                sql = schema_file.read_text(encoding="utf-8")
                try:
                    conn.execute(sql)
                    conn.commit()
                    logger.info("Database schema created successfully.")
                except Exception as e:
                    logger.error(f"Error creating schema: {e}")
                    conn.rollback()

        # 3. Seed users
        try:
            from .security import hash_password
            conn.execute("""
                INSERT INTO users (email, password_hash, full_name, role) VALUES 
                (%s, %s, %s, %s),
                (%s, %s, %s, %s)
                ON CONFLICT (lower(email)) DO NOTHING;
            """, (
                "shopper@likeness.dev", hash_password("shopper123"), "Demo Shopper", "customer",
                "admin@likeness.dev", hash_password("admin123"), "Store Admin", "admin"
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"User seed notice: {e}")
            conn.rollback()

        # 4. Seed categories
        try:
            conn.execute("""
                INSERT INTO categories (name, slug) VALUES 
                ('Dresses', 'dresses'),
                ('Tops', 'tops'),
                ('Skirts', 'skirts'),
                ('Sweaters', 'sweaters')
                ON CONFLICT (name) DO NOTHING;
            """)
            conn.commit()
        except Exception as e:
            logger.warning(f"Category seed notice: {e}")
            conn.rollback()

        # 5. Seed default products if empty
        try:
            p_count = conn.execute("SELECT count(*) AS count FROM products").fetchone()
            if not p_count or p_count.get("count", 0) == 0:
                cats = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories").fetchall()}
                sample_items = [
                    ("Sky Summer Dress", "Dresses", 9399, 20),
                    ("Orange Polka Dot Midi Dress", "Dresses", 6699, 5),
                    ("Mustard Floral Summer Dress", "Dresses", 9199, 8),
                    ("Teal Striped Midi Dress", "Dresses", 8299, 12),
                    ("Sky Striped Cotton Top", "Tops", 5799, 15),
                    ("Black Checked Boxy Top", "Tops", 10899, 8),
                    ("Forest Tee", "Tops", 9299, 10),
                    ("Teal Polka Dot A-line Skirt", "Skirts", 11599, 12),
                    ("Forest Floral A-line Skirt", "Skirts", 8199, 6),
                    ("Navy Checked Crew Sweater", "Sweaters", 7999, 14),
                    ("Ivory Knit Sweater", "Sweaters", 11299, 9),
                    ("Mustard Polka Dot Cosy Jumper", "Sweaters", 5599, 11),
                ]
                for name, cat_name, price, stock in sample_items:
                    cat_id = cats.get(cat_name)
                    if cat_id:
                        conn.execute("""
                            INSERT INTO products (category_id, name, description, price_cents, stock, image_path, is_active)
                            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                        """, (cat_id, name, f"A classic {name.lower()} in soft, breathable fabric.", price, stock, ""))
                conn.commit()
                logger.info("Sample products seeded successfully.")
        except Exception as e:
            logger.warning(f"Product seed notice: {e}")
            conn.rollback()
