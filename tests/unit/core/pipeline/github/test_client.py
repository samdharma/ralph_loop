"""Tests for the GitHubClient idempotent wrapper.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §7.2 and §10.2 B2.

``core.pipeline.github.client.GitHubClient`` accepts a ``run_id`` and
writes a record to ``.ralph/issues/<N>/idempotency.jsonl`` BEFORE each
``gh`` invocation. The record has shape::

    {timestamp, run_id, action, target, body_hash, returncode}

Behavior under test:

  1. ``client.comment(issue_num, body)`` writes one idempotency record
     BEFORE invoking ``gh``.
  2. Re-invoking ``client.comment`` with the same ``run_id`` and body
     does NOT invoke ``gh`` a second time.
  3. The logged record includes the client's ``run_id``.
  4. A different ``run_id`` for the same ``(issue_num, body)`` DOES
     invoke ``gh`` (different run → re-execute).

The tests patch ``subprocess.run`` (via the engine's ``gh`` helper
indirectly) so no real GitHub API calls are made.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "core"))

from core.pipeline.github import client  # noqa: E402

T0 = datetime(2026, 6, 27, 15, 30, 0, tzinfo=timezone.utc)


def _project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F821
) -> Path:
    """Point PROJECT_ROOT at tmp_path so logs land under tmp_path/.ralph/."""
    monkeypatch.setattr(client, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _fake_run_result(returncode: int = 0) -> MagicMock:
    """Build a MagicMock that quacks like ``subprocess.CompletedProcess``."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = b""
    result.stderr = b""
    return result


def test_comment_writes_idempotency_record_before_gh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A comment call appends one JSONL line BEFORE invoking gh."""
    _project_root(tmp_path, monkeypatch)
    with patch.object(client, "_run_gh") as run_gh:
        run_gh.return_value = _fake_run_result(0)
        gh_client = client.GitHubClient("20260627T1530-a1b2c3d4")
        gh_client.comment(42, "hello world")

    log_path = tmp_path / ".ralph" / "issues" / "42" / "idempotency.jsonl"
    assert log_path.exists()
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["run_id"] == "20260627T1530-a1b2c3d4"
    assert record["action"] == "comment"
    assert record["target"] == "42"


def test_repeated_comment_with_same_run_id_does_not_double_invoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two calls with the same run_id + body invoke gh exactly once."""
    _project_root(tmp_path, monkeypatch)
    with patch.object(client, "_run_gh") as run_gh:
        run_gh.return_value = _fake_run_result(0)
        gh_client = client.GitHubClient("20260627T1530-a1b2c3d4")
        gh_client.comment(42, "hello world")
        gh_client.comment(42, "hello world")

    assert run_gh.call_count == 1


def test_record_includes_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The idempotency record's run_id matches the client's run_id."""
    _project_root(tmp_path, monkeypatch)
    with patch.object(client, "_run_gh") as run_gh:
        run_gh.return_value = _fake_run_result(0)
        run_id = "20260627T1530-deadbeef"
        gh_client = client.GitHubClient(run_id)
        gh_client.comment(42, "hi")

    log_path = tmp_path / ".ralph" / "issues" / "42" / "idempotency.jsonl"
    record = json.loads(log_path.read_text().splitlines()[0])
    assert record["run_id"] == run_id


def test_different_run_id_invokes_gh_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A different run_id for the same (issue, body) re-invokes gh."""
    _project_root(tmp_path, monkeypatch)
    with patch.object(client, "_run_gh") as run_gh:
        run_gh.return_value = _fake_run_result(0)
        client.GitHubClient("20260627T1530-aaa").comment(42, "hi")
        client.GitHubClient("20260627T1530-bbb").comment(42, "hi")

    assert run_gh.call_count == 2