from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limiter import limiter

router = APIRouter(prefix="/api/v1", tags=["placeholders"])


@router.post("/products/{product_id}/want", summary="想要统计占位")
@limiter.limit("20/minute")
async def product_want_placeholder(request: Request, product_id: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"商品 {product_id} 的想要统计将在后续里程碑实现。",
    )
