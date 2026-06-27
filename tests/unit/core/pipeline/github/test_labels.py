"""Tests for core.pipeline.github.labels (C1.6b)."""

from __future__ import annotations


class TestLabelsAtNewPath:
    """C1.6b: transition_label at new location."""

    def test_transition_label_importable(self) -> None:
        from core.pipeline.github.labels import transition_label

        assert callable(transition_label)

    def test_transition_label_accepts_known_args(self) -> None:
        """transition_label accepts the standard (issue_num, add, remove, ...) args."""
        import inspect

        from core.pipeline.github.labels import transition_label

        sig = inspect.signature(transition_label)
        params = sig.parameters
        assert "issue_num" in params
