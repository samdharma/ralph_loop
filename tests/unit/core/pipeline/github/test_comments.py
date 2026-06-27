"""Tests for core.pipeline.github.comments (C1.6c)."""

from __future__ import annotations


class TestCommentsAtNewPath:
    """C1.6c: gh_comment at new location."""

    def test_gh_comment_importable(self) -> None:
        from core.pipeline.github.comments import gh_comment

        assert callable(gh_comment)

    def test_gh_comment_accepts_known_args(self) -> None:
        """gh_comment accepts (issue_num, body, run_id) args."""
        import inspect

        from core.pipeline.github.comments import gh_comment

        sig = inspect.signature(gh_comment)
        params = sig.parameters
        assert "issue_num" in params
        assert "body" in params
