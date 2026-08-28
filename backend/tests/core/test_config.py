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
