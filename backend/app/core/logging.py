"""Structured JSON logging via loguru."""

from __future__ import annotations

import contextvars
import json
import sys
from typing import Any

from loguru import logger

from app.core.config import get_settings

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
pseudo_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pseudo", default=None
)
route_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "route", default=None
)
duration_ms_var: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "duration_ms", default=None
)


def _serialize(record: dict[str, Any]) -> str:
    payload: dict[str, Any] = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "request_id": request_id_var.get(),
        "pseudo": pseudo_var.get(),
        "route": route_var.get(),
        "duration_ms": duration_ms_var.get(),
    }
    extra = record.get("extra")
    if isinstance(extra, dict):
        # Loguru wraps user extra inside its own "extra" key
        inner = extra.get("extra") if "extra" in extra else extra
        if isinstance(inner, dict):
            for k, v in inner.items():
                payload[k] = v
    return json.dumps(payload, ensure_ascii=False, default=str)


def _json_sink(message: Any) -> None:
    # message is a loguru message object with .record
    record = message.record
    sys.stderr.write(_serialize(record) + "\n")


def configure_logging() -> None:
    settings = get_settings()
    try:
        logger.remove()
    except ValueError:
        pass
    logger.add(_json_sink, level=settings.log_level)


def get_logger():
    return logger
