"""Tests for core.pipeline.github.board (C1.6d)."""

from __future__ import annotations


class TestBoardAtNewPath:
    """C1.6d: sync_status / sync_closed at new location."""

    def test_sync_status_importable(self) -> None:
        from core.pipeline.github.board import sync_status

        assert callable(sync_status)

    def test_sync_closed_importable(self) -> None:
        from core.pipeline.github.board import sync_closed

        assert callable(sync_closed)
