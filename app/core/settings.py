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

    secret_key: str = Field(alias="SECRET_KEY")
    jwt_expire_minutes: int = Field(default=1440, alias="JWT_EXPIRE_MINUTES")  # 默认 1 天

    # Performance testing secret key for payment callback simulation
    perf_secret_key: str | None = Field(default=None, alias="PERF_SECRET_KEY")

    database_url: str = Field(alias="DATABASE_URL")
    database_proxy_url: str | None = Field(default=None, alias="DATABASE_PROXY_URL")
    pgbouncer_host: str = Field(default="localhost", alias="PGBOUNCER_HOST")
    pgbouncer_port: int = Field(default=5432, alias="PGBOUNCER_PORT")
    database_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=30, alias="DATABASE_MAX_OVERFLOW")

    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")
    waf_trust_proxy: bool = Field(default=True, alias="WAF_TRUST_PROXY")

    multi_category_enabled: bool = Field(default=True, alias="MULTI_CATEGORY_ENABLED")
    reservation_enabled: bool = Field(default=False, alias="RESERVATION_ENABLED")
    want_enabled: bool = Field(default=True, alias="WANT_ENABLED")
    soldout_style: Literal["hide", "disabled"] = Field(default="hide", alias="SOLDOUT_STYLE")
    reconciliation_csv_enabled: bool = Field(
        default=False, alias="RECONCILIATION_CSV_ENABLED"
    )
    reconciliation_report_dir: str | None = Field(
        default=None, alias="RECONCILIATION_REPORT_DIR"
    )
    reservation_reminder_minutes: int = Field(default=15, alias="RESERVATION_REMINDER_MINUTES")
    reservation_slot_granularity_minutes: int = Field(
        default=15,
        alias="RESERVATION_SLOT_GRANULARITY_MINUTES",
    )
    reservation_slot_capacity: int = Field(
        default=10,
        alias="RESERVATION_SLOT_CAPACITY",
    )
    static_match_time_window_min: int = Field(default=5, alias="STATIC_MATCH_TIME_WINDOW_MIN")
    delivery_radius_m: int = Field(default=1500, alias="DELIVERY_RADIUS_M")
    print_retry_max: int = Field(default=5, alias="PRINT_RETRY_MAX")
    print_recovery_interval_seconds: int = Field(
        default=60, alias="PRINT_RECOVERY_INTERVAL_SECONDS"
    )
    print_dispatch_mode: Literal["celery", "celery_with_local_fallback", "local_only"] = Field(
        default="celery_with_local_fallback",
        alias="PRINT_DISPATCH_MODE",
    )
    print_local_max_parallel: int = Field(default=4, alias="PRINT_LOCAL_MAX_PARALLEL")
    guest_session_ttl_minutes: int = Field(default=43200, alias="GUEST_SESSION_TTL_MINUTES")
    order_pending_timeout_minutes: int = Field(
        default=30, alias="ORDER_PENDING_TIMEOUT_MINUTES"
    )
    order_pending_cleanup_interval_seconds: int = Field(
        default=120, alias="ORDER_PENDING_CLEANUP_INTERVAL_SECONDS"
    )

    menu_cache_ttl_seconds: int = Field(default=240, alias="MENU_CACHE_TTL_SECONDS")
    merchant_ws_recent_minutes: int = Field(default=5, alias="MERCHANT_WS_RECENT_MINUTES")
    merchant_ws_buffer_size: int = Field(default=200, alias="MERCHANT_WS_BUFFER_SIZE")
    merchant_ws_send_timeout_seconds: float = Field(
        default=1.0,
        alias="MERCHANT_WS_SEND_TIMEOUT_SECONDS",
    )
    shop_profile_cache_url: str | None = Field(default=None, alias="SHOP_PROFILE_CACHE_URL")
    shop_profile_cache_key: str = Field(default="shop:profile", alias="SHOP_PROFILE_CACHE_KEY")
    shop_profile_file: str = Field(default="app/data/shop_profile.json", alias="SHOP_PROFILE_FILE")

    celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")
    celery_default_queue: str = Field(default="default", alias="CELERY_DEFAULT_QUEUE")
    print_job_queue_name: str = Field(default="print_jobs", alias="PRINT_JOB_QUEUE_NAME")
    printer_webhook_url: str | None = Field(default=None, alias="PRINTER_WEBHOOK_URL")
    printer_webhook_token: str | None = Field(default=None, alias="PRINTER_WEBHOOK_TOKEN")
    printer_timeout_seconds: int = Field(default=5, alias="PRINTER_TIMEOUT_SECONDS")

    ws_broadcast_url: str | None = Field(default=None, alias="WS_BROADCAST_URL")
    ws_broadcast_channel: str = Field(default="ws:merchant:broadcast", alias="WS_BROADCAST_CHANNEL")

    loyalty_points_ratio: float = Field(default=1.0, alias="LOYALTY_POINTS_RATIO")
    loyalty_points_min_order: float = Field(default=0.0, alias="LOYALTY_POINTS_MIN_ORDER")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str | None = Field(default=None, alias="LOG_FILE")
    log_dir: str = Field(default="logs", alias="LOG_DIR")
    allowed_origins_raw: str = Field(
        default="http://localhost:3000,http://localhost:5173", alias="ALLOWED_ORIGINS"
    )
    rate_limit_default: str = Field(default="300/minute", alias="RATE_LIMIT_DEFAULT")
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    perf_disable_http_overheads: bool = Field(
        default=False, alias="PERF_DISABLE_HTTP_OVERHEADS"
    )

    @field_validator("allowed_origins_raw", mode="before")
    def ensure_string(cls, value: str) -> str:
        return value or ""

    @field_validator("secret_key", "database_url", "celery_broker_url", mode="before")
    def ensure_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("该配置为必填项,不允许为空。")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.allowed_origins_raw.split(",")]
        return [origin for origin in origins if origin]

    @property
    def rate_limit_default_limits(self) -> list[str]:
        limits = [limit.strip() for limit in self.rate_limit_default.split(",")]
        return [limit for limit in limits if limit]

    @property
    def disable_http_overheads(self) -> bool:
        return self.perf_disable_http_overheads or self.app_env == "perf"

    @property
    def database_runtime_url(self) -> str:
        return self.database_proxy_url or self.database_url

    @property
    def alembic_sync_url(self) -> str:
        if "+asyncpg" in self.database_url:
            return self.database_url.replace("+asyncpg", "+psycopg")
        if "+psycopg2" in self.database_url:
            return self.database_url.replace("+psycopg2", "+psycopg")
        return self.database_url

    @property
    def resolved_ws_broadcast_url(self) -> str | None:
        return self.ws_broadcast_url or self.celery_broker_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
