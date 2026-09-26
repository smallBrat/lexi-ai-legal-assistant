"""Central configuration using Pydantic Settings."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    GEMINI_API_KEY: SecretStr
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: SecretStr
    SUPABASE_SERVICE_ROLE_KEY: SecretStr

    # Optional settings with defaults
    ENVIRONMENT: str = Field(default="development", alias="ENVIRONMENT")
    DEBUG: bool = Field(default=False, alias="DEBUG")
    MAX_PDF_PAGES: int = Field(default=100, ge=1, alias="MAX_PDF_PAGES")
    MAX_EXTRACTED_CHARACTERS: int = Field(
        default=300_000, ge=1, alias="MAX_EXTRACTED_CHARACTERS"
    )
    OCR_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, alias="OCR_TIMEOUT_SECONDS")

    # Embedding configuration
    EMBEDDING_OUTPUT_DIMENSIONALITY: int = Field(
        default=1536, ge=128, le=3072, alias="EMBEDDING_OUTPUT_DIMENSIONALITY"
    )

    # ChromaDB persistence directory. When unset, EmbeddingService falls back
    # to its built-in default (<project_root>/.chroma). Set on ephemeral hosts
    # (e.g. CHROMA_DB_PATH=/tmp/chroma on Render).
    CHROMA_DB_PATH: str | None = Field(default=None, alias="CHROMA_DB_PATH")

    # Frontend origin allowed by the CORS middleware. Unset in development
    # (localhost origins are always allowed); set in production deployments.
    FRONTEND_URL: str | None = Field(default=None, alias="FRONTEND_URL")

    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


# Cached settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Convenience accessors
def get_gemini_key() -> str:
    """Get the Gemini API key."""
    return get_settings().GEMINI_API_KEY.get_secret_value()


def get_supabase_url() -> str:
    """Get the Supabase URL."""
    return get_settings().SUPABASE_URL


def get_supabase_anon_key() -> str:
    """Get the Supabase anon key."""
    return get_settings().SUPABASE_ANON_KEY.get_secret_value()


def get_supabase_service_key() -> str:
    """Get the Supabase service role key."""
    return get_settings().SUPABASE_SERVICE_ROLE_KEY.get_secret_value()


def is_development() -> bool:
    """Check if running in development environment."""
    return get_settings().is_development()


def is_production() -> bool:
    """Check if running in production environment."""
    return get_settings().is_production()