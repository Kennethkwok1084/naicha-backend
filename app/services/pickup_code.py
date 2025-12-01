from __future__ import annotations

import secrets
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings
from app.models.orders import Order
from app.models.shop import ShopSetting

logger = get_logger(__name__)

_DIGITS_DEFAULT = 6
_DIGITS_MIN = 3
_DIGITS_MAX = 12
_CODE_MAX_LENGTH = 20
_SETTING_KEYS = ("pickup_code_prefix", "pickup_code_digits")
_ALPHABET = "0123456789"


def _normalize_prefix(raw: str | None, fallback: str = "") -> str:
    base = (raw or fallback or "").strip()
    if not base:
        return ""
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "-_#")
    return cleaned[:10].upper()


def _normalize_digits(raw: str | int | None) -> int:
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _DIGITS_DEFAULT
    return max(_DIGITS_MIN, min(_DIGITS_MAX, value))


async def _load_customization(session: AsyncSession, settings: Settings) -> Tuple[str, int]:
    prefix_source = settings.pickup_code_prefix
    digits_source: str | int | None = settings.pickup_code_digits

    try:
        result = await session.execute(
            select(ShopSetting.key, ShopSetting.value).where(ShopSetting.key.in_(_SETTING_KEYS))
        )
        for key, value in result.all():
            if key == "pickup_code_prefix":
                prefix_source = value
            elif key == "pickup_code_digits":
                digits_source = value
    except Exception:
        logger.warning("pickup_code.load_settings_failed")

    prefix = _normalize_prefix(prefix_source)
    digits = _normalize_digits(digits_source)
    max_digits = max(1, _CODE_MAX_LENGTH - len(prefix))
    if digits > max_digits:
        logger.info("pickup_code.digits_truncated", digits=digits, max_allowed=max_digits)
        digits = max_digits
    return prefix, digits


def _render_code(prefix: str, digits: int) -> str:
    numeric = "".join(secrets.choice(_ALPHABET) for _ in range(digits))
    return f"{prefix}{numeric}"


async def ensure_pickup_code(order: Order, session: AsyncSession, settings: Settings) -> str | None:
    if order.pickup_code:
        return order.pickup_code
    if order.payment_status != "paid":
        return None

    prefix, digits = await _load_customization(session, settings)
    code = _render_code(prefix, digits)
    order.pickup_code = code
    return code
