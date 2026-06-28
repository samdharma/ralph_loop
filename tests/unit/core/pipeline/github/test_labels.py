"""Tests for core.pipeline.github.labels (C1.6b)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest


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
        assert "add" in params
        assert "remove" in params
        assert "run_id" in params


class TestTransitionLabelRunIdRouting:
    """RALPH_RUN_ID selects GitHubClient idempotency path or direct gh."""

    @pytest.fixture(autouse=True)
    def _patch_emit_and_sync(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Trajectory and board sync must not touch the real filesystem."""
        monkeypatch.setattr(
            "core.pipeline.retry._emit_trajectory",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "core.project_sync.sync_status",
            lambda *args, **kwargs: None,
        )

    def test_transition_label_with_run_id_env_uses_github_client(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When RALPH_RUN_ID is set, transition_label routes through GitHubClient."""
        from core.pipeline.github import client as gh_client_mod
        from core.pipeline.github.labels import transition_label

        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("RALPH_RUN_ID", "run-123")

        ok = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with (
            mock.patch.object(gh_client_mod, "_run_gh", return_value=ok) as client_gh,
            mock.patch("core.pipeline.github.labels._run_gh") as direct_gh,
        ):
            transition_label(1, "status:design", "status:ready")

        assert client_gh.call_count == 1
        assert direct_gh.call_count == 0

    def test_transition_label_without_run_id_env_falls_back_to_direct_gh(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When RALPH_RUN_ID is unset, transition_label calls gh directly."""
        from core.pipeline.github import client as gh_client_mod
        from core.pipeline.github.labels import transition_label

        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.delenv("RALPH_RUN_ID", raising=False)

        ok = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with (
            mock.patch.object(gh_client_mod, "_run_gh") as client_gh,
            mock.patch(
                "core.pipeline.github.labels._run_gh", return_value=ok
            ) as direct_gh,
        ):
            transition_label(1, "status:design", "status:ready")

        assert direct_gh.call_count == 1
        assert client_gh.call_count == 0

    def test_transition_label_with_run_id_env_writes_idempotency_log(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """After a GitHubClient transition, .ralph/issues/<N>/idempotency.jsonl exists."""
        from core.pipeline.github import client as gh_client_mod
        from core.pipeline.github.labels import transition_label

        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("RALPH_RUN_ID", "run-123")

        ok = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch.object(gh_client_mod, "_run_gh", return_value=ok):
            transition_label(1, "status:design", "status:ready")

        log = tmp_path / ".ralph" / "issues" / "1" / "idempotency.jsonl"
        assert log.exists()
        records = [json.loads(line) for line in log.read_text().splitlines()]
        assert any(r["action"] == "transition_label" for r in records)
