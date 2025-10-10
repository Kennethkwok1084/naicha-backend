from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_env: Literal["dev", "staging", "prod"] = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    secret_key: str = Field(default="change_me", alias="SECRET_KEY")
    jwt_expire_minutes: int = Field(default=43200, alias="JWT_EXPIRE_MINUTES")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:Onjuju1084@localhost:5432/naicha",
        alias="DATABASE_URL",
    )
    pgbouncer_host: str = Field(default="localhost", alias="PGBOUNCER_HOST")
    pgbouncer_port: int = Field(default=5432, alias="PGBOUNCER_PORT")

    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")
    waf_trust_proxy: bool = Field(default=True, alias="WAF_TRUST_PROXY")

    multi_category_enabled: bool = Field(default=True, alias="MULTI_CATEGORY_ENABLED")
    reservation_enabled: bool = Field(default=False, alias="RESERVATION_ENABLED")
    want_enabled: bool = Field(default=True, alias="WANT_ENABLED")
    soldout_style: Literal["hide", "disabled"] = Field(default="hide", alias="SOLDOUT_STYLE")
    reservation_reminder_minutes: int = Field(default=15, alias="RESERVATION_REMINDER_MINUTES")
    static_match_time_window_min: int = Field(default=5, alias="STATIC_MATCH_TIME_WINDOW_MIN")
    delivery_radius_m: int = Field(default=1500, alias="DELIVERY_RADIUS_M")
    print_retry_max: int = Field(default=5, alias="PRINT_RETRY_MAX")
    guest_session_ttl_minutes: int = Field(default=43200, alias="GUEST_SESSION_TTL_MINUTES")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    allowed_origins_raw: str = Field(
        default="http://localhost:3000,http://localhost:5173", alias="ALLOWED_ORIGINS"
    )

    @field_validator("allowed_origins_raw", mode="before")
    def ensure_string(cls, value: str) -> str:
        return value or ""

    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.allowed_origins_raw.split(",")]
        return [origin for origin in origins if origin]

    @property
    def alembic_sync_url(self) -> str:
        if "+asyncpg" in self.database_url:
            return self.database_url.replace("+asyncpg", "+psycopg")
        if "+psycopg2" in self.database_url:
            return self.database_url.replace("+psycopg2", "+psycopg")
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
