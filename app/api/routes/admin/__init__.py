from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import get_auth_service
from app.core.security import TokenScope
from app.schemas import AdminLoginRequestSchema, TokenSchema
from app.services.auth import AuthService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/login", response_model=TokenSchema)
async def admin_login(
    payload: AdminLoginRequestSchema, auth_service: AuthService = Depends(get_auth_service)
) -> TokenSchema:
    admin = await auth_service.authenticate_admin(payload.username, payload.password)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_service.issue_access_token(subject=str(admin.admin_id), scope=TokenScope.ADMIN)
    return TokenSchema(access_token=token)
