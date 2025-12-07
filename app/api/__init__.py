from fastapi import APIRouter

from app.api.routes import (
    admin,
    advertisements,
    analytics,
    config,
    guests,
    me,
    menu,
    ops,
    orders,
    payments,
    shop,
    system,
    users,
    want,
    wechat_auth,
    ws,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(config.router)
api_router.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
api_router.include_router(advertisements.router)
api_router.include_router(analytics.router)
api_router.include_router(wechat_auth.router)
# DEPRECATED: 旧users路由已改为/users-legacy前缀，暂时保留但不推荐使用
api_router.include_router(users.router)  # 使用users-legacy前缀，不与wechat_auth冲突
api_router.include_router(guests.router)
api_router.include_router(me.router)
api_router.include_router(menu.router)
api_router.include_router(shop.router)
api_router.include_router(orders.router)
api_router.include_router(payments.router)
api_router.include_router(payments.legacy_router)
api_router.include_router(want.router)
api_router.include_router(ws.router)
api_router.include_router(ops.router)
api_router.include_router(config.admin_router)
