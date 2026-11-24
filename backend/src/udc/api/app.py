"""FastAPI application factory (Phase 3 will add all routers)."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from udc.api.dependencies import check_api_key, get_mapping_store, get_source_store
from udc.api.routers.mappings import router as mappings_router
from udc.api.routers.schemas import router as schemas_router
from udc.api.routers.sources import coverage_router
from udc.api.routers.sources import router as sources_router
from udc.core.config import get_settings
from udc.core.logging import setup_logging
from udc.demo import seed_demo

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    try:
        settings = get_settings()
    except ValidationError:
        settings = None  # endpoints that need settings report the problem themselves
    if settings is not None and settings.seed_demo:
        added = seed_demo(get_source_store(settings), get_mapping_store(settings))
        log.info("Demo seed: added %s", ", ".join(added) or "nothing (already present)")
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Universal Data Connector",
        version="0.1.0",
        description="Map any data source to a canonical schema using LLM-powered inference.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    # /health stays open for the host's health checks; everything else is
    # guarded when REQUIRE_API_KEY is set (public deployments).
    guarded = [Depends(check_api_key)]
    application.include_router(mappings_router, dependencies=guarded)
    application.include_router(schemas_router, dependencies=guarded)
    application.include_router(sources_router, dependencies=guarded)
    application.include_router(coverage_router, dependencies=guarded)

    return application


app = create_app()
