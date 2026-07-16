from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    app_version: str
    debug: bool
    database_url: str

    api_prefix: str = "/api/v1"
    secret_key: str
    access_token_expire_minutes: int = 60

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
        return self


settings = Settings()
