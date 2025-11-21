from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.metrics.config import CONFIG_REQUEST_TOTAL
from app.models.accounts import Admin
from app.schemas import (
    FeatureToggleRequestSchema,
    FeatureToggleResponseSchema,
    PublicConfigSchema,
)
from app.services.config import (
    ConfigService,
    PublicConfigNotConfiguredError,
    PublicConfigValidationError,
)

router = APIRouter(prefix="/api/v1/config", tags=["config"])
admin_router = APIRouter(prefix="/api/v1/admin/config", tags=["admin-config"])

_CONFIG_ADMIN_ALLOWED_ROLES = {"admin", "manager"}


async def get_config_service(
    session: AsyncSession = Depends(get_async_session),
) -> ConfigService:
    return ConfigService(session, get_settings())


@router.get(
    "",
    response_model=PublicConfigSchema,
    summary="获取公共配置",
)
async def fetch_public_config(
    service: ConfigService = Depends(get_config_service),
) -> PublicConfigSchema:
    try:
        payload = await service.get_public_config()
        CONFIG_REQUEST_TOTAL.labels(result="success").inc()
        return PublicConfigSchema.model_validate(payload)
    except (PublicConfigNotConfiguredError, PublicConfigValidationError) as exc:
        CONFIG_REQUEST_TOTAL.labels(result="error").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@admin_router.put(
    "/features/{feature_key}",
    response_model=FeatureToggleResponseSchema,
    summary="更新功能开关",
)
async def update_feature_toggle(
    feature_key: str,
    payload: FeatureToggleRequestSchema,
    admin: Admin = Depends(get_current_admin),
    service: ConfigService = Depends(get_config_service),
) -> FeatureToggleResponseSchema:
    if admin.role not in _CONFIG_ADMIN_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权更新配置。",
        )

    try:
        config = await service.update_feature_flag(
            feature_key,
            enabled=payload.enabled,
            admin_id=admin.admin_id,
            reason=payload.reason,
        )
    except PublicConfigValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return FeatureToggleResponseSchema(
        config_key=config.config_key,
        value=bool(config.value_json),
        updated_at=config.updated_at,
        updated_by_admin_id=config.updated_by_admin_id,
    )
