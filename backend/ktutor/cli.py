"""Shim: ``ktutor.cli`` re-exports the canonical CLI app from ``app.cli``."""

from app.cli import app

__all__ = ["app"]
