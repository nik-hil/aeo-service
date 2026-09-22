"""FastAPI application factory / module path for uvicorn."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aeo_mvp.api.routes import api_router, router
from aeo_mvp.config import get_settings
from aeo_mvp.db.session import init_db
from aeo_mvp.logging_config import setup_logging
from aeo_mvp.security.api_auth import ApiAuthMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    settings = get_settings()
    logger.info(
        "startup paid_retrieval_opt_in=%s (AEO_PAID_RETRIEVAL_OPT_IN; "
        "ADR-026 still requires ready QuerySet + DO credentials)",
        str(bool(settings.paid_retrieval_opt_in)).lower(),
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AEO MVP API",
        version="0.1.0",
        description=(
            "Backend-only Answer Engine Optimization service. "
            "Visibility experiments are controlled samples (vis-exp-v1), not engine rankings. "
            "Application routes require Authorization: Bearer <AEO_API_KEY>."
        ),
        lifespan=lifespan,
    )
    # Auth runs for every request (including trailing-slash / docs aliases) before routing.
    app.add_middleware(ApiAuthMiddleware)
    app.include_router(router)
    app.include_router(api_router)
    return app


app = create_app()
