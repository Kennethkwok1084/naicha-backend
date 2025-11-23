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
    detail = exc.detail
    message: str
    extra: dict[str, Any] | None = None
    if isinstance(detail, dict):
        message = str(detail.get("message") or "")
        extra = {key: value for key, value in detail.items() if key != "message"}
    else:
        message = str(detail)
    content = _build_error_payload(message, exc.status_code, extra=extra)
    content["detail"] = message
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    message = "Request validation failed."
    # Serialize error objects to avoid "Object of type ValueError is not JSON serializable"
    errors = []
    for err in exc.errors():
        serialized_err = {
            "type": err.get("type"),
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "input": err.get("input"),
        }
        # Convert ctx values to strings if present
        if err.get("ctx"):
            serialized_err["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
        errors.append(serialized_err)

    content = _build_error_payload(
        message,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        extra={"details": errors},
    )
    content["detail"] = message
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=content)


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    structlog.get_logger("app").exception("Unhandled exception", error=str(exc))
    message = "Internal server error."
    content = _build_error_payload(message, status.HTTP_500_INTERNAL_SERVER_ERROR)
    content["detail"] = message
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=content)


def init_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
