"""Global FastAPI exception handlers — structured JSON error responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def _error(request: Request, status: int, type_: str, detail: str) -> JSONResponse:
    log.warning(
        "%s %s → %d %s: %s",
        request.method,
        request.url.path,
        status,
        type_,
        detail,
    )
    return JSONResponse(
        status_code=status,
        content={"error": type_, "detail": detail, "path": str(request.url.path)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach structured-JSON handlers for common Python exceptions."""

    @app.exception_handler(KeyError)
    async def _key_error(request: Request, exc: KeyError) -> JSONResponse:
        return _error(request, 404, "NotFound", str(exc))

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
        return _error(request, 422, "ValidationError", str(exc))

    @app.exception_handler(PermissionError)
    async def _permission_error(request: Request, exc: PermissionError) -> JSONResponse:
        return _error(request, 403, "Forbidden", str(exc))
