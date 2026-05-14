from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/omniship_poc",
        alias="DATABASE_URL",
    )
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    omniship_base_url: str = Field(
        default="https://crossborder.omniship.eu", alias="OMNISHIP_BASE_URL"
    )
    omniship_login_url: str = Field(
        default="https://crossborder.omniship.eu/", alias="OMNISHIP_LOGIN_URL"
    )
    omniship_air_waybills_url: str = Field(
        default="https://crossborder.omniship.eu/air_waybills",
        alias="OMNISHIP_AIR_WAYBILLS_URL",
    )
    omniship_air_waybills_create_url: str = Field(
        default="https://crossborder.omniship.eu/air_waybills/create",
        alias="OMNISHIP_AIR_WAYBILLS_CREATE_URL",
    )
    omniship_username: str = Field(default="", alias="OMNISHIP_USERNAME")
    omniship_password: str = Field(default="", alias="OMNISHIP_PASSWORD")
    playwright_headless: bool = Field(default=True, alias="PLAYWRIGHT_HEADLESS")
    playwright_timeout_ms: int = Field(default=30_000, alias="PLAYWRIGHT_TIMEOUT_MS")
    alline_pre_alert_upload_timeout_ms: int = Field(
        default=180_000,
        alias="ALLINE_PRE_ALERT_UPLOAD_TIMEOUT_MS",
    )
    alline_preview_validation_timeout_ms: int = Field(
        default=120_000,
        alias="ALLINE_PREVIEW_VALIDATION_TIMEOUT_MS",
    )
    omniship_incremental_stop_after_unchanged: int = Field(
        default=10, alias="OMNISHIP_INCREMENTAL_STOP_AFTER_UNCHANGED"
    )
    air_waybill_auto_refresh_enabled: bool = Field(
        default=True,
        alias="AIR_WAYBILL_AUTO_REFRESH_ENABLED",
    )
    air_waybill_auto_refresh_interval_seconds: int = Field(
        default=3600,
        alias="AIR_WAYBILL_AUTO_REFRESH_INTERVAL_SECONDS",
    )
    air_waybill_auto_refresh_initial_delay_seconds: int = Field(
        default=3600,
        alias="AIR_WAYBILL_AUTO_REFRESH_INITIAL_DELAY_SECONDS",
    )
    auth_session_ttl_hours: int = Field(default=12, alias="AUTH_SESSION_TTL_HOURS")
    auth_cookie_secure: bool = Field(default=False, alias="AUTH_COOKIE_SECURE")
    auth_cookie_name: str = Field(default="integrer_session", alias="AUTH_COOKIE_NAME")
    upload_storage_dir: Path = Field(
        default=BACKEND_DIR / "storage" / "uploads",
        alias="UPLOAD_STORAGE_DIR",
    )

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
