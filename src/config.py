from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Config the OTEL SDK does not already read for itself from OTEL_* env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"


# ponytail: module-level singleton. Becomes a get_settings() dependency the day
# something needs to override it in a test.
settings = Settings()
