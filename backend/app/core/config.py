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
    # Comma-separated list of allowed origins for CORS (s09). The
    # operator must keep this in sync with the frontend's
    # ``NEXT_PUBLIC_API_URL`` host (or its expected ``Origin`` header).
    # ``cors_allow_origins_list`` parses the raw string into a list of
    # origins (with whitespace stripped and empties dropped).
    cors_allow_origins: str = "http://localhost:3000"
    # Safety net below the chat stream's chunk counter — if a runaway
    # agent yields more than this many chunks, the SSE router stops the
    # stream. Defaults to a high but finite value.
    chat_stream_max_chunks: int = 5000
    # Heartbeat interval in milliseconds (s09 D6). 0 = disabled (YAGNI).
    chat_stream_heartbeat_ms: int = 0

    @property
    def cors_allow_origins_list(self) -> list[str]:
        """Parse ``cors_allow_origins`` into a list of trimmed origins."""
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]

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

    # Free-style exercise generation (s06 — probleme / redaction).
    # ``free_difficulty_options`` is a comma-separated string parsed by the
    # CLI at wire-up time (convention s03 ``qcm_max_questions``).
    free_default_difficulty: str = "moyen"
    free_difficulty_options: str = "facile,moyen,difficile"
    free_max_retries: int = 1
    free_temperature: float = 0.0
    # Safety net below the String(8192) column ceiling — a 192-char margin
    # so the generator raises ``statement_too_long`` before the DB rejects
    # the row.
    free_max_statement_chars: int = 8000

    # Flashcard deck generation (s06b — flashcards).
    # Default number of cards when ``--n`` is not provided.
    flashcards_default_n: int = 10
    # Hard cap on the number of cards per generation.
    flashcards_max_n: int = 30
    # Number of retry attempts when the LLM returns malformed JSON, or when
    # the post-Pydantic check (duplicate fronts, external references) fires.
    flashcards_max_retries: int = 1
    # Sampling temperature for flashcard generation. 0 for reproducibility.
    flashcards_temperature: float = 0.0
    # Maximum length of a card's ``front`` (question) — enforced by the
    # Pydantic ``max_length`` and re-checked after retry.
    flashcards_max_front_chars: int = 200
    # Maximum length of a card's ``back`` (answer) — same rationale.
    flashcards_max_back_chars: int = 200

    # Free-form text grader (s07 — submit-text, probleme / redaction).
    # The grader is an LLM-as-judge: it compares the student's answer
    # against ``Exercise.expected_answer`` and ``grading_criteria``.
    # Number of retry attempts when the LLM output cannot be parsed
    # against the strict ``VERDICT:`` regex. Pattern mirrors s03 /
    # s06 / s06b above.
    text_grader_max_retries: int = 1
    # Sampling temperature for the text grader. 0 keeps the verdict
    # reproducible (within the non-determinism budget of the upstream
    # LLM provider).
    text_grader_temperature: float = 0.0
    # Safety net below the String(8192) column ceiling of
    # ``Attempt.answer_text`` (models.py:194) — a 192-char margin so
    # the grader raises ``answer_too_long`` before the DB rejects the
    # row. The CLI ``submit-text`` enforces the same limit at the
    # Pydantic ``max_length`` boundary.
    text_grader_max_answer_chars: int = 8000

    # Progressive correction (s08 — correction progressive des exercices).
    # Max attempts before the exercise is closed (correction_level
    # ``full_after_attempts``). A 4th submission raises
    # ``ProgressiveCorrectionError("closed")`` and the CLI maps it to
    # exit 6.
    max_correction_attempts: int = 3


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
