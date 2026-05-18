"""FinAlly FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.watchlist import router as watchlist_router
from app.db import WatchlistRepo
from app.market import PriceCache, create_market_data_source, create_stream_router

logger = logging.getLogger(__name__)

# This file is backend/app/main.py, so parents[2] is the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app() -> FastAPI:
    """Construct the FastAPI app."""
    # The PriceCache is constructed up-front so the SSE router can close over it.
    # The market data source is started in the lifespan and writes into this cache.
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repo = WatchlistRepo()
        source = create_market_data_source(cache)
        initial_tickers = repo.list_tickers()
        logger.info("Starting market data source with %d tickers", len(initial_tickers))
        await source.start(initial_tickers)

        app.state.repo = repo
        app.state.cache = cache
        app.state.source = source

        try:
            yield
        finally:
            logger.info("Stopping market data source")
            await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.state.cache = cache

    # API routes
    app.include_router(watchlist_router)
    app.include_router(create_stream_router(cache))

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Serve the static frontend (single-page app).
    if FRONTEND_DIR.exists():
        index_path = FRONTEND_DIR / "index.html"

        @app.get("/")
        async def root():
            if index_path.exists():
                return FileResponse(index_path)
            return JSONResponse({"detail": "Frontend not built yet"}, status_code=503)

        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    else:
        @app.get("/")
        async def root():
            return JSONResponse({"detail": "Frontend not built yet"}, status_code=503)

    return app


app = create_app()
