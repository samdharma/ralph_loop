"""Tests for core.pipeline.recovery (C1.7c)."""

from __future__ import annotations


class TestRecoveryAtNewPath:
    """C1.7c: crash recovery helpers at new location."""

    def test_recover_from_crash_importable(self) -> None:
        from core.pipeline.recovery import recover_from_crash

        assert callable(recover_from_crash)
