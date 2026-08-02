from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings the OpenTelemetry SDK does not read for itself from OTEL_* variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"

    # Baked into the image at build time. Ties a trace to the commit that produced it.
    service_version: str = Field(default="unknown", validation_alias="GIT_SHA")

    # SecretStr masks the value in logs and tracebacks. Read it with .get_secret_value().
    honeycomb_api_key: SecretStr | None = Field(default=None, validation_alias="HONEYCOMB_API_KEY")

    # Defaults to the docker-compose database. A deployed service overrides it, and the
    # DSN carries a password, so it is masked like any other credential.
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://rag:rag@localhost:5433/rag"),
        validation_alias="DATABASE_URL",
    )


settings = Settings()
