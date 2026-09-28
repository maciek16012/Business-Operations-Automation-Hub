from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Business Operations Automation Hub"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+asyncpg://boah:boah_dev_password@postgres:5432/boah"
    storage_backend: Literal["filesystem"] = "filesystem"
    storage_path: str = "/data/documents"
    ocr_enabled: bool = False
    ocr_tesseract_url: str = "http://localhost:8011/ocr"
    ocr_paddle_url: str = "http://localhost:8012/ocr"
    ocr_tesseract_profile: str = "baseline"
    ocr_paddle_profile: str = "baseline"
    max_upload_bytes: int = 5 * 1024 * 1024
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
