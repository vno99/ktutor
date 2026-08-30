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

    # File Storage (S3-compatible, SeaweedFS in local dev / CI)
    s3_endpoint: str = "localhost:8333"
    s3_access_key: str = "ktutorci"
    s3_secret_key: str = "ktutorci_secret"
    s3_bucket: str = "assistant-documents"

    # Uploads
    max_upload_size_mb: int = 20

    # LLM / Embeddings
    llm_provider: Literal["minimax", "openai", "mistral", "ollama"] = "minimax"
    openai_api_key: str = ""

    # Chat LLM (s02) — the maths agent pipeline. The ``minimax`` provider is
    # routed via OpenRouter (an OpenAI-compatible endpoint). ``openai`` is
    # served directly. ``ollama`` is intentionally not wired (raises
    # ``NotImplementedError`` at factory time) — wiring ollama requires
    # adding ``langchain-ollama`` to ``requirements.txt`` (out of s02 scope).
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "minimax/minimax-m3:free"
    chat_temperature: float = 0.0
    chat_top_k: int = 4
    chat_no_document_message: str = (
        "Je n'ai pas trouvé d'information sur ce sujet dans tes documents."
    )

    # QCM generation (s03)
    qcm_default_questions: int = 5
    qcm_max_questions: int = 20
    qcm_max_retries: int = 1
    qcm_temperature: float = 0.0


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
