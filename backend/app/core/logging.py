"""Structured JSON logging via loguru."""

from __future__ import annotations

import json
import sys
from typing import Any

from loguru import logger

from app.core.config import get_settings


def _serialize(record: dict[str, Any]) -> str:
    """Serialize a loguru record to a JSON string."""
    payload: dict[str, Any] = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
    }
    extra = record.get("extra")
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Configure loguru to emit structured JSON to stderr."""
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="{message}",
        serialize=False,
        filter=lambda record: record.update(_extra := {}),
    )
    # Patch the sink to wrap text as JSON
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=lambda record: _serialize(record) + "\n",
    )


def get_logger():
    """Return the configured loguru logger."""
    return logger
