"""Top-level ``ktutor`` package — thin alias over ``app``.

This exists so that the user-facing command promised by the design
(``python -m ktutor.cli upload …``) works without renaming the canonical
``app`` package referenced in ``docs/architecture.md``.
"""

from app.cli import app as cli_app

__all__ = ["cli_app"]
