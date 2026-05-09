"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from udc.api.errors import register_exception_handlers
from udc.api.routers.connectors import router as connectors_router
from udc.api.routers.data import router as data_router
from udc.api.routers.jobs import router as jobs_router
from udc.api.routers.mappings import router as mappings_router
from udc.api.routers.schema_diff import router as schema_diff_router
from udc.core.logging import setup_logging


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
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

    application.include_router(connectors_router)
    application.include_router(jobs_router)
    application.include_router(mappings_router)
    application.include_router(data_router)
    application.include_router(schema_diff_router)

    register_exception_handlers(application)

    return application


app = create_app()
