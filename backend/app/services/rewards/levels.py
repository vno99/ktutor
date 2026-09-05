"""Level calculation (s20a, AC6)."""

from __future__ import annotations

LEVEL_APPRENTI = "Apprenti"
LEVEL_CONFIRME = "Confirmé"
LEVEL_EXPERT = "Expert"


# Thresholds defined in the story / research.
LEVEL_THRESHOLDS = [
    (0, 99, LEVEL_APPRENTI),
    (100, 499, LEVEL_CONFIRME),
    (500, float("inf"), LEVEL_EXPERT),
]


def get_level(points: int) -> str:
    """Calculate the level label from total points (AC6 / D4 recommendation B)."""
    for min_pts, max_pts, label in LEVEL_THRESHOLDS:
        if min_pts <= points <= max_pts:
            return label
    return LEVEL_APPRENTI  # defensive fallback
