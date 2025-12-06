"""Admin 认证相关接口"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from structlog import get_logger

from app.api.dependencies.auth import get_auth_service, get_current_admin
from app.core.permissions import get_permissions_for_role
from app.core.security import TokenScope
from app.metrics.auth import ADMIN_LOGIN_TOTAL
from app.models.accounts import Admin
from app.schemas import AdminInfoSchema, AdminLoginRequestSchema, AdminLoginResponseSchema
from app.services.auth import AuthService

router = APIRouter()
logger = get_logger(__name__)


@router.post("/login", response_model=AdminLoginResponseSchema)
async def admin_login(
    payload: AdminLoginRequestSchema, auth_service: AuthService = Depends(get_auth_service)
) -> AdminLoginResponseSchema:
    """管理员登录，返回 token 和用户信息"""
    admin = await auth_service.authenticate_admin(payload.username, payload.password)
    if not admin:
        ADMIN_LOGIN_TOTAL.labels(result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_service.issue_access_token(subject=str(admin.admin_id), scope=TokenScope.ADMIN)
    permissions = list(get_permissions_for_role(admin.role))

    ADMIN_LOGIN_TOTAL.labels(result="success").inc()

    return AdminLoginResponseSchema(
        access_token=token,
        admin=AdminInfoSchema(
            id=str(admin.admin_id),
            username=admin.username,
            role=admin.role,
            permissions=permissions,
        ),
    )


@router.get("/me", response_model=AdminInfoSchema)
async def get_current_admin_info(
    admin: Admin = Depends(get_current_admin),
) -> AdminInfoSchema:
    """获取当前登录管理员信息"""
    permissions = list(get_permissions_for_role(admin.role))

    return AdminInfoSchema(
        id=str(admin.admin_id),
        username=admin.username,
        role=admin.role,
        permissions=permissions,
    )
