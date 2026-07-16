from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    app_version: str
    debug: bool
    database_url: str

    api_prefix: str = "/api/v1"
    secret_key: str
    access_token_expire_minutes: int = 60
    environment: Literal["development", "testing", "production"] = "development"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_pool_size: int = Field(default=10, ge=1, le=50)
    database_max_overflow: int = Field(default=20, ge=0, le=100)
    database_pool_recycle_seconds: int = Field(default=1800, ge=300, le=86400)
    scheduler_enabled: bool = True

    # Email Settings
    email_address: str
    email_password: str
    email_recipient: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    @model_validator(mode="after")
    def validate_production_security(self):
        if not self.debug and len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters outside development")
        if not 5 <= self.access_token_expire_minutes <= 1440:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 1440")
        if self.environment == "production" and self.debug:
            raise ValueError("DEBUG must be false in production")
        if any(not origin.startswith(("http://", "https://")) for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must contain absolute HTTP or HTTPS origins")
        if self.environment == "production" and any(not origin.startswith("https://") or "localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins):
            raise ValueError("Production CORS_ORIGINS must contain only production HTTPS origins")
        if self.environment == "production" and any(marker in self.secret_key.lower() for marker in ("replace", "change-me", "validation-only")):
            raise ValueError("Production SECRET_KEY still contains a placeholder value")
        if self.environment == "production" and any(marker in self.database_url.lower() for marker in ("replace", "change-me")):
            raise ValueError("Production DATABASE_URL still contains a placeholder value")
        return self


settings = Settings()
