import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, FRONTEND_URLS, UPLOAD_DIR, validate_settings
from .db import check_connection, pool
from .embedder import warm_up
from .routers import admin, auth, cart, catalog, orders


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings()
    pool.open()
    check_connection()
    # warm_up is deferred so the server starts immediately and stays within memory limits
    yield
    pool.close()


app = FastAPI(title="Likeness API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_URLS,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, catalog.router, cart.router, orders.router, admin.router):
    app.include_router(r)

app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="media")


INDEX_FILE = BASE_DIR / "index.html"
if not INDEX_FILE.exists():
    INDEX_FILE = BASE_DIR.parent / "index.html"

CONFIG_JS = BASE_DIR / "supabase-config.js"
if not CONFIG_JS.exists():
    CONFIG_JS = BASE_DIR.parent / "supabase-config.js"


@app.get("/", include_in_schema=False)
def root():
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return {
        "status": "Likeness API is live",
        "health": "/api/health",
        "docs": "/docs",
        "products": "/api/products",
    }


@app.get("/supabase-config.js", include_in_schema=False)
def get_supabase_config():
    if CONFIG_JS.exists():
        return FileResponse(CONFIG_JS)
    return ""


@app.get("/api/health")
def health():
    check_connection()
    return {"ok": True, "database": "connected"}
