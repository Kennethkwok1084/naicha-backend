from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings
from app.models.shop import ShopConfig

logger = get_logger(__name__)
_CONFIG_CACHE_CLIENT: Redis | None = None
_ALLOWED_FEATURE_KEYS = {"disable_delivery", "disable_coupons", "disable_stamps"}


class PublicConfigNotConfiguredError(Exception):
    """未能加载到静态配置文件。"""


class PublicConfigValidationError(Exception):
    """静态配置格式不合法。"""


class ConfigService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    def _get_cache_client(self) -> Redis | None:
        global _CONFIG_CACHE_CLIENT
        if _CONFIG_CACHE_CLIENT is not None:
            return _CONFIG_CACHE_CLIENT
        try:
            _CONFIG_CACHE_CLIENT = from_url(
                self._settings.celery_broker_url, decode_responses=True
            )
        except Exception as exc:  # pragma: no cover - 初始化失败仅记录
            logger.warning("config.cache_client_init_failed", error=str(exc))
            return None
        return _CONFIG_CACHE_CLIENT

    def _resolve_config_file(self) -> Path:
        raw_path = Path(self._settings.public_config_file)
        if not raw_path.is_absolute():
            base_dir = Path(__file__).resolve().parents[2]
            raw_path = base_dir / raw_path
        return raw_path

    async def get_public_config(self) -> dict[str, Any]:
        cached_payload = await self._read_public_config_from_cache()
        if cached_payload is not None:
            await self._merge_feature_flags(cached_payload)
            return cached_payload

        static_config = self._read_public_config_file()
        await self._merge_feature_flags(static_config)

        ttl_seconds = self._resolve_cache_ttl(static_config)
        await self._write_public_config_to_cache(static_config, ttl_seconds)
        return static_config

    async def _merge_feature_flags(self, payload: dict[str, Any]) -> None:
        feature_flags = await self._fetch_feature_flags()
        merged_features = dict(payload.get("features") or {})
        merged_features.update(feature_flags)
        payload["features"] = merged_features

    def _read_public_config_file(self) -> dict[str, Any]:
        file_path = self._resolve_config_file()
        if not file_path.exists():
            raise PublicConfigNotConfiguredError("公共配置文件不存在。")

        try:
            content = file_path.read_text(encoding="utf-8")
            payload = json.loads(content)
        except OSError as exc:
            raise PublicConfigNotConfiguredError("读取公共配置文件失败。") from exc
        except json.JSONDecodeError as exc:
            raise PublicConfigValidationError("公共配置文件格式错误。") from exc

        if not isinstance(payload, dict):
            raise PublicConfigValidationError("公共配置文件内容需为对象。")
        return payload

    async def _read_public_config_from_cache(self) -> dict[str, Any] | None:
        client = self._get_cache_client()
        if client is None:
            return None
        try:
            raw_value = await client.get(self._settings.public_config_cache_key)
        except RedisError as exc:
            logger.warning("config.cache_read_failed", error=str(exc))
            return None

        if raw_value is None:
            return None

        try:
            payload = json.loads(raw_value)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.warning("config.cache_decode_failed")
        return None

    async def _write_public_config_to_cache(self, payload: dict[str, Any], ttl_seconds: int) -> None:
        client = self._get_cache_client()
        if client is None:
            return
        try:
            await client.setex(
                self._settings.public_config_cache_key,
                ttl_seconds,
                json.dumps(payload, ensure_ascii=False),
            )
        except RedisError as exc:
            logger.warning("config.cache_write_failed", error=str(exc))

    async def _invalidate_cache(self) -> None:
        client = self._get_cache_client()
        if client is None:
            return
        try:
            await client.delete(self._settings.public_config_cache_key)
        except RedisError as exc:
            logger.warning("config.cache_delete_failed", error=str(exc))

    async def _fetch_feature_flags(self) -> dict[str, bool]:
        stmt = select(ShopConfig.config_key, ShopConfig.value_json).where(
            ShopConfig.category == "features"
        )
        result = await self._session.execute(stmt)
        features: dict[str, bool] = {}
        for config_key, value in result.all():
            if not config_key.startswith("features."):
                continue
            _, _, suffix = config_key.partition(".")
            features[suffix] = bool(value)
        return features

    def _resolve_cache_ttl(self, payload: dict[str, Any]) -> int:
        ttl = payload.get("ttl_seconds")
        if isinstance(ttl, int) and ttl > 0:
            return ttl
        return max(self._settings.public_config_cache_ttl_seconds, 60)

    async def update_feature_flag(
        self,
        key: str,
        enabled: bool,
        admin_id: int | None,
        reason: str | None = None,
    ) -> ShopConfig:
        if key not in _ALLOWED_FEATURE_KEYS:
            raise PublicConfigValidationError("不支持的功能开关键。")
        full_key = f"features.{key}"
        instance = await self._session.get(ShopConfig, full_key)
        if instance is None:
            instance = ShopConfig(
                config_key=full_key,
                value_json=enabled,
                category="features",
                description=(reason or None),
                updated_by_admin_id=admin_id,
            )
            self._session.add(instance)
        else:
            instance.value_json = enabled
            instance.description = reason or instance.description
            instance.updated_by_admin_id = admin_id

        await self._session.commit()
        await self._session.refresh(instance)
        await self._invalidate_cache()
        return instance
