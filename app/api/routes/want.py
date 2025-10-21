from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user_optional
from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.schemas import WantRecordResponseSchema
from app.services.want import (
    WantFeatureDisabledError,
    WantRateLimitError,
    WantService,
    WantTargetNotFoundError,
)

router = APIRouter(prefix="/api/v1", tags=["want"])


async def get_want_service(
    session: AsyncSession = Depends(get_async_session),
) -> WantService:
    return WantService(session, get_settings())


def _want_rate_limit_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return get_remote_address(request)


@router.post(
    "/products/{product_id}/want",
    response_model=WantRecordResponseSchema,
    summary="提交想要记录",
)
@limiter.limit("20/minute", key_func=_want_rate_limit_key)
async def create_want_event(
    request: Request,
    response: Response,
    product_id: int,
    current_user=Depends(get_current_user_optional),
    service: WantService = Depends(get_want_service),
) -> WantRecordResponseSchema:
    if current_user:
        request.state.user_id = current_user.user_id

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    try:
        event = await service.record_want(
            product_id=product_id,
            user=current_user,
            ip=client_ip,
            user_agent=user_agent,
            now=datetime.now(tz=UTC),
        )
    except WantFeatureDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WantTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except WantRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    return WantRecordResponseSchema(
        product_id=event.product_id,
        created_at=event.created_at,
        source="user" if current_user else "guest",
    )
