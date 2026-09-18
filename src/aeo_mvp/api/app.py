"""FastAPI application factory / module path for uvicorn."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from aeo_mvp.api.routes import api_router, router
from aeo_mvp.db.session import init_db
from aeo_mvp.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AEO MVP API",
        version="0.1.0",
        description=(
            "Backend-only Answer Engine Optimization service. "
            "Visibility experiments are controlled samples (vis-exp-v1), not engine rankings."
        ),
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(api_router)
    return app


app = create_app()
