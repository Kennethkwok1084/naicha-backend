from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.schemas import PaymentNotifyResponseSchema, WechatPaymentNotifySchema
from app.services.payments import (
    PaymentConflictError,
    PaymentOrderNotFoundError,
    PaymentService,
    PaymentServiceError,
    PaymentSignatureError,
)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


async def get_payment_service(
    session: AsyncSession = Depends(get_async_session),
) -> PaymentService:
    return PaymentService(session, get_settings())


@router.post(
    "/notify/wechat",
    response_model=PaymentNotifyResponseSchema,
    summary="微信支付回调",
)
@limiter.limit("120/minute")
async def wechat_payment_notify(
    request: Request,
    response: Response,
    service: PaymentService = Depends(get_payment_service),
) -> PaymentNotifyResponseSchema:
    raw_body = await request.body()
    signature = request.headers.get("X-Wechat-Signature", "")

    try:
        payload = WechatPaymentNotifySchema.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid notification payload.",
        ) from exc

    try:
        result = await service.handle_wechat_notification(
            payload,
            raw_body=raw_body,
            signature=signature,
        )
    except PaymentSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except PaymentOrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PaymentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return PaymentNotifyResponseSchema(**result)
