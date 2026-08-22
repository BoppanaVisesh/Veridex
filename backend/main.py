"""
Veridex NBA Platform — Application Entry Point

Starts the FastAPI server, mounts frontend, and seeds historical data.
"""

from __future__ import annotations

import os
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn

from backend.learning_service import learning_service


# ── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    """Seed historical data on first startup."""
    from backend.database import db

    existing = db.get_all_decisions(limit=1)
    if not existing:
        print("[Veridex] Seeding historical outcomes for learning loop warm-start...")
        count = learning_service.seed_historical_outcomes()
        print(f"[Veridex] Seeded {count} historical outcomes across 9 decision types")
    else:
        print(f"[Veridex] Database already contains decisions, skipping seed")
    yield


# ── Re-create app with lifespan ────────────────────────────────────────────
from backend.api import app as _app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Veridex - Intelligent Next Best Action Platform",
    description="Agentic Decision Intelligence for Product Catalog Operations",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Copy all routes from the api module
for route in _app.routes:
    app.routes.append(route)

from backend.catalog.catalog_api import router as catalog_router
app.include_router(catalog_router)

# Mount Frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[Veridex] Starting Intelligent NBA Platform on http://localhost:8000")
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

