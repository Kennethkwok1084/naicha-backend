from fastapi import APIRouter

from app.api.routes import (
    admin,
    guests,
    me,
    menu,
    orders,
    payments,
    placeholders,
    shop,
    system,
    ws,
    users,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(admin.router)
api_router.include_router(users.router)
api_router.include_router(guests.router)
api_router.include_router(me.router)
api_router.include_router(menu.router)
api_router.include_router(shop.router)
api_router.include_router(orders.router)
api_router.include_router(payments.router)
api_router.include_router(placeholders.router)
