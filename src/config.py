from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Config the OTEL SDK does not already read for itself from OTEL_* env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"

    # SecretStr, so that logging a Settings object, or letting one reach a traceback,
    # prints '**********' instead of the key. Read it with .get_secret_value().
    honeycomb_api_key: SecretStr | None = Field(default=None, validation_alias="HONEYCOMB_API_KEY")


# ponytail: module-level singleton. Becomes a get_settings() dependency the day
# something needs to override it in a test.
settings = Settings()
