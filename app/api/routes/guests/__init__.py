from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas import GuestSessionCreateRequestSchema, GuestSessionResponseSchema
from app.services.guest import GuestSessionService

router = APIRouter(prefix="/api/v1/guests", tags=["guests"])


async def get_guest_session_service(
    session: AsyncSession = Depends(get_async_session),
) -> GuestSessionService:
    return GuestSessionService(session)


@router.post("/session", response_model=GuestSessionResponseSchema, summary="创建或续期游客会话")
async def create_guest_session(
    payload: GuestSessionCreateRequestSchema = Body(default=GuestSessionCreateRequestSchema()),
    service: GuestSessionService = Depends(get_guest_session_service),
) -> GuestSessionResponseSchema:
    session_id, expires_at = await service.issue_session(payload.session_token)
    return GuestSessionResponseSchema(guest_session_id=session_id, expires_at=expires_at)
