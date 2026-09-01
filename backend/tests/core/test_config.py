"""Tests for the application configuration loader."""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


class TestSettingsDefaults:
    """Settings come with sensible defaults so the CLI is usable out of the box."""

    def test_default_max_upload_size_is_20mb(self) -> None:
        settings = Settings()
        assert settings.max_upload_size_mb == 20

    def test_default_vision_provider_is_deepseek_ocr_2(self) -> None:
        settings = Settings()
        assert settings.vision_provider == "deepseek-ocr-2"

    def test_default_deepseek_ocr_url_is_local(self) -> None:
        settings = Settings()
        assert settings.deepseek_ocr_url == "http://localhost:8500"

    def test_get_settings_returns_singleton(self) -> None:
        a = get_settings()
        b = get_settings()
        assert a is b


class TestSettingsFromEnv:
    """Environment variables override defaults."""

    def test_max_upload_size_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "50")
        settings = Settings()
        assert settings.max_upload_size_mb == 50

    def test_vision_provider_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VISION_PROVIDER", "openai")
        settings = Settings()
        assert settings.vision_provider == "openai"

    def test_invalid_vision_provider_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VISION_PROVIDER", "bogus-provider")
        # Pydantic validation error on construction.
        import pytest as _pytest

        with _pytest.raises(Exception):
            Settings()


class TestQcmSettings:
    """QCM generation settings — s03."""

    def test_default_qcm_default_questions_is_5(self) -> None:
        assert Settings().qcm_default_questions == 5

    def test_default_qcm_max_questions_is_20(self) -> None:
        assert Settings().qcm_max_questions == 20

    def test_default_qcm_max_retries_is_1(self) -> None:
        assert Settings().qcm_max_retries == 1

    def test_default_qcm_temperature_is_zero(self) -> None:
        assert Settings().qcm_temperature == 0.0

    def test_qcm_default_questions_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QCM_DEFAULT_QUESTIONS", "8")
        assert Settings().qcm_default_questions == 8

    def test_qcm_max_questions_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QCM_MAX_QUESTIONS", "30")
        assert Settings().qcm_max_questions == 30


class TestFreeSettings:
    """Free-style exercise generation settings — s06 (probleme, redaction)."""

    def test_default_free_default_difficulty_is_moyen(self) -> None:
        assert Settings().free_default_difficulty == "moyen"

    def test_default_free_difficulty_options_is_facile_moyen_difficile(self) -> None:
        assert Settings().free_difficulty_options == "facile,moyen,difficile"

    def test_default_free_max_retries_is_1(self) -> None:
        assert Settings().free_max_retries == 1

    def test_default_free_temperature_is_zero(self) -> None:
        assert Settings().free_temperature == 0.0

    def test_default_free_max_statement_chars_is_8000(self) -> None:
        # Below the String(8192) column ceiling — a safety net so the
        # generator raises ``statement_too_long`` before the DB rejects.
        assert Settings().free_max_statement_chars == 8000

    def test_free_default_difficulty_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FREE_DEFAULT_DIFFICULTY", "difficile")
        assert Settings().free_default_difficulty == "difficile"


class TestChatSettings:
    """Chat LLM settings — s02."""

    def test_default_chat_top_k_is_4(self) -> None:
        assert Settings().chat_top_k == 4

    def test_default_chat_temperature_is_zero(self) -> None:
        assert Settings().chat_temperature == 0.0

    def test_default_llm_base_url_is_openrouter(self) -> None:
        assert Settings().llm_base_url == "https://openrouter.ai/api/v1"

    def test_default_no_document_message_set(self) -> None:
        assert "tes documents" in Settings().chat_no_document_message

    def test_chat_top_k_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHAT_TOP_K", "8")
        assert Settings().chat_top_k == 8

    def test_llm_model_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
        assert Settings().llm_model == "openai/gpt-4o-mini"

    def test_llm_api_key_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_API_KEY", "sk-test-xyz")
        assert Settings().llm_api_key == "sk-test-xyz"
