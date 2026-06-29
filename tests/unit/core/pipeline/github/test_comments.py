"""Tests for core.pipeline.github.comments (C1.6c)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest


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
        assert "run_id" in params


class TestGhCommentRunIdRouting:
    """RALPH_RUN_ID selects GitHubClient idempotency path or direct gh."""

    @pytest.fixture(autouse=True)
    def _patch_emit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Trajectory emission must not write to the real filesystem."""
        monkeypatch.setattr(
            "core.pipeline.retry._emit_trajectory",
            lambda *args, **kwargs: None,
        )

    def test_gh_comment_with_run_id_env_uses_github_client(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When RALPH_RUN_ID is set, gh_comment routes through GitHubClient."""
        from core.pipeline.github import client as gh_client_mod
        from core.pipeline.github.comments import gh_comment

        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("RALPH_RUN_ID", "run-123")

        ok = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with (
            mock.patch.object(gh_client_mod, "_run_gh", return_value=ok) as client_gh,
            mock.patch("core.pipeline.github.comments._run_gh") as direct_gh,
        ):
            result = gh_comment(1, "hello")

        assert result is True
        assert client_gh.call_count == 1
        assert direct_gh.call_count == 0

    def test_gh_comment_without_run_id_env_falls_back_to_direct_gh(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When RALPH_RUN_ID is unset, gh_comment calls gh directly."""
        from core.pipeline.github import client as gh_client_mod
        from core.pipeline.github.comments import gh_comment

        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.delenv("RALPH_RUN_ID", raising=False)

        ok = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with (
            mock.patch.object(gh_client_mod, "_run_gh") as client_gh,
            mock.patch(
                "core.pipeline.github.comments._run_gh", return_value=ok
            ) as direct_gh,
        ):
            result = gh_comment(1, "hello")

        assert result is True
        assert direct_gh.call_count == 1
        assert client_gh.call_count == 0

    def test_gh_comment_with_run_id_env_writes_idempotency_log(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """After a GitHubClient comment, .ralph/issues/<N>/idempotency.jsonl exists."""
        from core.pipeline.github import client as gh_client_mod
        from core.pipeline.github.comments import gh_comment

        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("RALPH_RUN_ID", "run-123")

        ok = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch.object(gh_client_mod, "_run_gh", return_value=ok):
            gh_comment(1, "hello")

        log = tmp_path / ".ralph" / "issues" / "1" / "idempotency.jsonl"
        assert log.exists()
        records = [json.loads(line) for line in log.read_text().splitlines()]
        assert any(r["action"] == "comment" for r in records)
