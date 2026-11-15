import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_URLS, UPLOAD_DIR, validate_settings
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


@app.get("/", include_in_schema=False)
def root():
    return {
        "status": "Likeness API is live",
        "health": "/api/health",
        "docs": "/docs",
        "products": "/api/products",
    }


@app.get("/api/health")
def health():
    check_connection()
    return {"ok": True, "database": "connected"}
