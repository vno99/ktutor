"""Tests for level thresholds (s20a, AC6)."""

from __future__ import annotations

from app.services.rewards.levels import LEVEL_APPRENTI, LEVEL_CONFIRME, LEVEL_EXPERT, get_level


class TestLevels:
    def test_apprenti_at_0_points(self) -> None:
        assert get_level(0) == LEVEL_APPRENTI

    def test_apprenti_at_99_points(self) -> None:
        assert get_level(99) == LEVEL_APPRENTI

    def test_confirme_at_100_points(self) -> None:
        assert get_level(100) == LEVEL_CONFIRME

    def test_confirme_at_499_points(self) -> None:
        assert get_level(499) == LEVEL_CONFIRME

    def test_expert_at_500_points(self) -> None:
        assert get_level(500) == LEVEL_EXPERT

    def test_expert_at_512_points(self) -> None:
        assert get_level(512) == LEVEL_EXPERT
