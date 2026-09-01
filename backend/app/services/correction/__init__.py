"""Progressive correction service (s08).

This package owns the 4-state correction flow (partial /
partial_attempt_2 / full / full_after_attempts) for both QCM (s04)
and free-form text (s07) exercises. The service is consumed by the
``submit-qcm`` and ``submit-text`` CLI commands via a ``grade_callback``
callable — the service does NOT modify the s04 or s07 graders.
"""

from __future__ import annotations

from app.services.correction.progressive import (
    CorrectionLevel,
    CorrectionResult,
    ProgressiveCorrectionError,
    ProgressiveCorrectionService,
    next_correction_level,
)

__all__ = [
    "CorrectionLevel",
    "CorrectionResult",
    "ProgressiveCorrectionError",
    "ProgressiveCorrectionService",
    "next_correction_level",
]
