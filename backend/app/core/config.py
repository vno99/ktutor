"""Pydantic Settings for ktutor backend configuration."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql://ktutor:ktutor@localhost:5432/ktutor"
    database_pool_size: int = 20

    # Vector Store
    chroma_persist_directory: str = "./chroma_data"
    chroma_server_url: str = "http://localhost:8500"

    # Vision (OCR)
    vision_provider: Literal["deepseek-ocr-2", "openai", "gemini"] = "deepseek-ocr-2"
    deepseek_ocr_url: str = "http://localhost:8500"
    deepseek_ocr_timeout: int = 60

    # File Storage
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "ktutor"
    minio_secret_key: str = "ktutor-secret"
    minio_bucket: str = "assistant-documents"

    # Uploads
    max_upload_size_mb: int = 20

    # LLM / Embeddings
    llm_provider: Literal["minimax", "openai", "mistral", "ollama"] = "minimax"
    openai_api_key: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a process-wide singleton ``Settings`` instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset the cached settings instance (used in tests)."""
    global _settings
    _settings = None
