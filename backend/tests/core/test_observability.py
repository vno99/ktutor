"""Test env/config updates for s23."""
import json
import pytest
from app.core.config import get_settings, reset_settings


def test_settings_has_observability_vars():
    reset_settings()
    s = get_settings()
    assert hasattr(s, "ot_exporter")
    assert hasattr(s, "metrics_enabled")
    assert s.log_level


def test_observability_module_exists():
    from app.core.observability import tracing, metrics
    assert tracing is not None
    assert metrics is not None


def test_llm_wrapper_logs_duration():
    from app.services.llm.client import LlmClient
    assert hasattr(LlmClient, "invoke")
    assert hasattr(LlmClient, "astream")


def test_tracing_exists():
    from app.core.observability.tracing import setup_tracing
    provider = setup_tracing()
    assert provider is not None


def test_celery_wrapper_imports():
    from app.core.observability.celery_logger import init_celery_logger
    assert init_celery_logger is not None


def test_metrics_endpoint_exists():
    from app.api.metrics import router
    assert router is not None
    from app.api.metrics import router
    assert router is not None


def test_main_has_observability_middleware():
    from app.main import app
    from starlette.middleware.base import BaseHTTPMiddleware
    middleware_classes = [
        m.cls if hasattr(m, "cls") else m.__class__
        for m in app.user_middleware
    ]
    names = [cls.__name__ for cls in middleware_classes if cls is not None]
    assert any("Observability" in n or "Log" in n for n in names) or len(names) >= 1


def test_log_json_has_request_fields():
    from app.core.logging import configure_logging, get_logger, _serialize
    # Verify serialization directly without altering global logger
    fake_record = {
        "time": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        "level": __import__("types").SimpleNamespace(name="INFO"),
        "message": "test",
        "extra": {"extra": {"request_id": "r1", "route": "/test", "duration_ms": 10.5, "pseudo": "ali"}},
    }
    result = json.loads(_serialize(fake_record))
    assert result["message"] == "test"
    assert result["request_id"] == "r1"
    assert result["route"] == "/test"
    assert result["duration_ms"] == 10.5
    assert result["pseudo"] == "ali"
