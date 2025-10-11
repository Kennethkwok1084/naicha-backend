from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user_optional
from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.schemas import (
    OrderCreateRequestSchema,
    OrderPaymentInitiateResponseSchema,
    OrderResponseSchema,
    OrderPaymentJsapiRequestSchema,
    OrderPaymentNativeRequestSchema,
)
from app.services.orders import (
    OrderConflictError,
    OrderNotFoundError,
    OrderOwnershipError,
    OrderService,
    OrderValidationError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


async def get_order_service(
    session: AsyncSession = Depends(get_async_session),
) -> OrderService:
    return OrderService(session, get_settings())


@router.post("", response_model=OrderResponseSchema, summary="创建订单")
@limiter.limit("30/minute")
async def create_order(
    request: Request,
    response: Response,
    service: OrderService = Depends(get_order_service),
    current_user=Depends(get_current_user_optional),
) -> OrderResponseSchema:
    idempotency_key = request.headers.get("Idempotency-Key", "")

    try:
        raw_body = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body.",
        ) from exc

    try:
        payload = OrderCreateRequestSchema.model_validate(raw_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    try:
        result = await service.create_order(
            payload=payload,
            idempotency_key=idempotency_key,
            user=current_user,
        )
    except OrderValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OrderConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return OrderResponseSchema(**result)


@router.post(
    "/{order_id}/pay/jsapi",
    response_model=OrderPaymentInitiateResponseSchema,
    summary="发起微信 JSAPI 支付",
)
@limiter.limit("60/minute")
async def initiate_jsapi_payment(
    request: Request,
    order_id: int,
    response: Response,
    service: OrderService = Depends(get_order_service),
    current_user=Depends(get_current_user_optional),
) -> OrderPaymentInitiateResponseSchema:
    try:
        raw_body = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body.",
        ) from exc

    try:
        payload = OrderPaymentJsapiRequestSchema.model_validate(raw_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    try:
        result = await service.initiate_wechat_jsapi_payment(
            order_id=order_id,
            actor=current_user,
            request=payload,
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrderConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return OrderPaymentInitiateResponseSchema(**result)


@router.post(
    "/{order_id}/pay/native",
    response_model=OrderPaymentInitiateResponseSchema,
    summary="发起微信 Native 支付",
)
@limiter.limit("60/minute")
async def initiate_native_payment(
    request: Request,
    order_id: int,
    response: Response,
    service: OrderService = Depends(get_order_service),
    current_user=Depends(get_current_user_optional),
) -> OrderPaymentInitiateResponseSchema:
    try:
        raw_body = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body.",
        ) from exc

    try:
        payload = OrderPaymentNativeRequestSchema.model_validate(raw_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    try:
        result = await service.initiate_wechat_native_payment(
            order_id=order_id,
            actor=current_user,
            request=payload,
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrderConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return OrderPaymentInitiateResponseSchema(**result)
