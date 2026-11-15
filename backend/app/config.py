import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
PRODUCT_DIR = UPLOAD_DIR / "products"
PRODUCT_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_HOURS = 24 * 7
# Comma-separated list. This makes local development and a deployed frontend work
# together without falling back to an unrestricted CORS policy.
FRONTEND_URLS = tuple(
    url.strip().rstrip("/")
    for url in os.getenv("FRONTEND_URLS", "http://localhost:5173").split(",")
    if url.strip()
)
FRONTEND_URL = FRONTEND_URLS[0]
CURRENCY = os.getenv("CURRENCY", "usd").lower()
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def validate_settings() -> None:
    """Fail at startup instead of accidentally connecting to a local database."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required. Set it to your Supabase Postgres connection URI.")
    if not DATABASE_URL.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URI.")
    if len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters.")
