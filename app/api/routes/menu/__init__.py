from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_async_session
from app.schemas import MenuResponseSchema
from app.services.menu import MenuService

router = APIRouter(prefix="/api/v1/menu", tags=["menu"])


async def get_menu_service(
    session: AsyncSession = Depends(get_async_session),
) -> MenuService:
    return MenuService(session, get_settings())


@router.get("", response_model=MenuResponseSchema, summary="获取菜单")
async def fetch_menu(service: MenuService = Depends(get_menu_service)) -> MenuResponseSchema:
    payload = await service.get_menu_payload()
    return MenuResponseSchema(**payload)
