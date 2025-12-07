"""Admin API 路由聚合器"""

from __future__ import annotations

from fastapi import APIRouter

from . import ads, auth, dashboard, inventory, orders, payments, pos, products, want

router = APIRouter()

# 注册子路由
router.include_router(auth.router, tags=["admin-auth"])
router.include_router(pos.router, tags=["admin-pos"])
router.include_router(payments.router, tags=["admin-payments"])
router.include_router(dashboard.router, tags=["admin-dashboard"])
router.include_router(inventory.router, tags=["admin-inventory"])
router.include_router(want.router, tags=["admin-want"])
router.include_router(ads.router, tags=["admin-ads"])
router.include_router(orders.router, tags=["admin-orders"])
router.include_router(products.router, tags=["admin-products"], prefix="/products")

__all__ = ["router"]
