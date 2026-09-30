from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    auth_enabled: bool = True
    auth_cookie_secure: bool = False
    auth_session_hours: int = 8
    boah_master_key: str = Field(default="", repr=False)
    boah_master_key_file: str = ""
    boah_initial_admin_email: str = ""
    boah_initial_admin_password: str = Field(default="", repr=False)
    boah_service_token: str = Field(default="", repr=False)
    mounted_roots: dict[str, str] = {}
    connector_network_allowlist: list[str] = []
    connector_allow_plaintext_test: bool = False
    debug: bool = False
    public_url: str = "http://localhost:3000"
    delivery_max_attempts: int = 5
    delivery_retry_seconds: int = 30
    app_name: str = "Business Operations Automation Hub"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: str = "http://localhost:3000"
    database_url: str = Field(
        default="postgresql+asyncpg://boah:boah_dev_password@postgres:5432/boah", repr=False
    )
    storage_backend: Literal["filesystem"] = "filesystem"
    storage_path: str = "/data/documents"
    ocr_enabled: bool = False
    ocr_tesseract_url: str = "http://localhost:8011/ocr"
    ocr_paddle_url: str = "http://localhost:8012/ocr"
    ocr_tesseract_profile: str = "baseline"
    ocr_paddle_profile: str = "baseline"
    stp_enabled: bool = False
    stp_primary_ocr_provider: Literal["tesseract", "paddle"] = "paddle"
    stp_native_min_chars_per_page: float = 100.0
    stp_native_min_alnum_ratio: float = 0.30
    stp_native_min_printable_ratio: float = 0.95
    stp_native_min_text_page_ratio: float = 0.80
    stp_native_max_image_area_ratio: float = 0.80
    stp_target_rate: float = 0.90
    stp_require_zero_critical_false_accepts: bool = True
    adaptive_extraction_enabled: bool = True
    security_preflight_enabled: bool = True
    security_fail_closed: bool = True
    security_max_attachment_bytes: int = 5 * 1024 * 1024
    security_allowed_mime_types: str = "application/pdf,image/png,image/jpeg,image/tiff,text/plain"
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 30.0
    review_notifications_enabled: bool = True
    review_notification_webhook_url: str = "http://n8n:5678/webhook/boah-review-m5"
    review_notification_timeout_seconds: float = 15.0
    max_upload_bytes: int = 5 * 1024 * 1024
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @field_validator("security_fail_closed")
    @classmethod
    def require_fail_closed(cls, value: bool) -> bool:
        if not value:
            raise ValueError("M5 does not support fail-open security")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
