from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = Field(
        description="PostgreSQL connection string for the demo / target database"
    )

    # LLM
    anthropic_api_key: str = Field(description="Anthropic API key for Claude")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude model to use for schema mapping",
    )

    # DuckDB
    duckdb_path: str = Field(
        default="./data/udc.duckdb",
        description="Path to the DuckDB file used for local storage and querying",
    )

    # API
    api_key: str = Field(
        default="dev-secret",
        description="Static API key for the FastAPI backend (override in production)",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")

    # App
    app_env: str = Field(default="development", description="'development' or 'production'")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
