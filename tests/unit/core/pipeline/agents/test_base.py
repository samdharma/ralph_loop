"""Tests for worktree setup/teardown helper.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §10.2 B3 and plan §3 R-5 mitigation.

``core.pipeline.agents.base`` exposes:

  - :func:`create_worktree` — create a worktree for issue_num at a
    deterministic path, with a pre-flight ``git worktree add`` check.
  - :func:`remove_worktree` — tear down a worktree, removing it from
    ``git worktree list``.

Tests cover:

  1. ``create_worktree`` invokes ``git worktree add`` and returns the
    worktree path.
  2. ``remove_worktree`` invokes ``git worktree remove``.
  3. Pre-flight check: when ``git worktree add`` fails, ``create_worktree``
    raises ``RuntimeError`` with a clear message.
  4. Linux: ``src/`` inside the worktree is mounted read-only after
    ``create_worktree`` (B3.2 placeholder; full mount coverage in B3.2
    tests, see TestReadOnlySrc).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "core"))

from core.pipeline.agents import base  # noqa: E402


def test_create_worktree_invokes_git_worktree_add(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create_worktree calls git worktree add and returns the worktree path."""
    monkeypatch.setattr(base, "PROJECT_ROOT", tmp_path)

    fake_result = mock.Mock(returncode=0, stdout=b"", stderr=b"")

    with mock.patch.object(base, "_run_git", return_value=fake_result) as run_git:
        wt_path = base.create_worktree(42)

    # The first _run_git call is the pre-flight check.
    assert run_git.call_count >= 1
    # One of the calls must be the actual create.
    add_called = any(
        "worktree" in call.args[0] and "add" in call.args[0]
        for call in run_git.call_args_list
    )
    assert add_called
    assert wt_path.exists()


def test_remove_worktree_invokes_git_worktree_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """remove_worktree calls git worktree remove."""
    monkeypatch.setattr(base, "PROJECT_ROOT", tmp_path)

    fake_result = mock.Mock(returncode=0, stdout=b"", stderr=b"")
    wt_path = tmp_path / ".ralph" / "worktrees" / "1"

    with mock.patch.object(base, "_run_git", return_value=fake_result) as run_git:
        base.remove_worktree(wt_path)

    remove_called = any(
        "worktree" in call.args[0] and "remove" in call.args[0]
        for call in run_git.call_args_list
    )
    assert remove_called


def test_create_worktree_preflight_raises_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When git worktree fails, create_worktree raises RuntimeError."""
    monkeypatch.setattr(base, "PROJECT_ROOT", tmp_path)

    # Pre-flight git worktree add fails.
    fail_result = mock.Mock(returncode=1, stdout=b"", stderr=b"fatal: bad")
    with mock.patch.object(base, "_run_git", return_value=fail_result):
        with pytest.raises(RuntimeError) as exc_info:
            base.create_worktree(1)

    assert "git worktree" in str(exc_info.value).lower()