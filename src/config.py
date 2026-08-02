from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings the OpenTelemetry SDK does not read for itself from OTEL_* variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"

    # SecretStr masks the value in logs and tracebacks. Read it with .get_secret_value().
    honeycomb_api_key: SecretStr | None = Field(default=None, validation_alias="HONEYCOMB_API_KEY")


settings = Settings()
