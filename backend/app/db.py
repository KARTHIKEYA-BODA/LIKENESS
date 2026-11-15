from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL, validate_settings

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
