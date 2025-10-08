from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limiter import limiter

router = APIRouter(prefix="/api/v1", tags=["placeholders"])


@router.post("/orders", summary="创建订单占位")
@limiter.limit("30/minute")
async def create_order_placeholder(request: Request) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="订单创建将在后续里程碑实现。",
    )


@router.post("/payments/notify/wechat", summary="支付回调占位")
@limiter.limit("120/minute")
async def wechat_payment_callback_placeholder(request: Request) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="微信支付回调将在后续里程碑实现。",
    )


@router.post("/products/{product_id}/want", summary="想要统计占位")
@limiter.limit("20/minute")
async def product_want_placeholder(request: Request, product_id: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"商品 {product_id} 的想要统计将在后续里程碑实现。",
    )
