from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status


def _build_error_payload(
    message: str, code: int, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    ctx = structlog.contextvars.get_contextvars()
    payload: dict[str, Any] = {
        "error": {
            "message": message,
            "code": code,
            "trace_id": ctx.get("trace_id"),
        }
    }
    if extra:
        payload["error"].update(extra)
    return payload


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_payload(exc.detail, exc.status_code),
        headers=exc.headers,
    )


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_build_error_payload(
            "Request validation failed.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            extra={"details": exc.errors()},
        ),
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    structlog.get_logger("app").exception("Unhandled exception", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_payload(
            "Internal server error.", status.HTTP_500_INTERNAL_SERVER_ERROR
        ),
    )


def init_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
