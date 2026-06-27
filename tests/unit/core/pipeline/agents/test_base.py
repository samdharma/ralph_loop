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
    wt_path.mkdir(parents=True)

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


class TestReadOnlySrc:
    """B3.2: read-only src/ enforcement.

    Per spec §10.2 B3 and plan §3 R-5 mitigation:
      - Linux: ``mount --bind src /tmp/ralph-wt/src && mount -o
        remount,ro,bind /tmp/ralph-wt/src`` (true mechanism isolation).
      - macOS: ``chmod -R 0500 src/`` (writes enforced, reads policy-only)
        + WARNING log.
      - On mount failure on Linux, fall back to ``chmod -R 0500 src/``.

    Tests assert:
      1. On Linux mock: mount command is invoked.
      2. On macOS mock: chmod 0500 is applied AND a WARNING is logged.
      3. remove_worktree reverses the read-only state.
    """

    def test_linux_uses_mount_bind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Linux path: create_worktree invokes mount --bind + mount -o remount,ro,bind."""
        monkeypatch.setattr(base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(base.sys, "platform", "linux")

        # Bypass pre-flight and the worktree add git call.
        monkeypatch.setattr(base, "_preflight_check", lambda: None)
        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True)
        src_dir = wt_path / "src"
        src_dir.mkdir()

        with (
            mock.patch.object(base, "_run_git", return_value=mock.Mock(returncode=0)),
            mock.patch.object(base, "_run_mount") as run_mount,
        ):
            base._enforce_readonly_src(wt_path)

        # At least one mount call must reference bind + remount,ro,bind.
        all_calls = [c.args[0] for c in run_mount.call_args_list]
        assert any(
            "--bind" in cmd and "remount" in cmd and "ro" in cmd for cmd in all_calls
        ), f"expected mount --bind + remount,ro,bind; got {all_calls}"

    def test_macos_uses_chmod_0500(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
    ) -> None:
        """macOS path: chmod -R 0500 src/ is applied AND a WARNING is logged."""
        import logging

        monkeypatch.setattr(base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(base.sys, "platform", "darwin")

        monkeypatch.setattr(base, "_preflight_check", lambda: None)
        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True)
        src_dir = wt_path / "src"
        src_dir.mkdir()
        (src_dir / "foo.py").write_text("x = 1\n")

        with (
            mock.patch.object(base, "_run_git", return_value=mock.Mock(returncode=0)),
            mock.patch.object(base, "_run_mount") as run_mount,
            caplog.at_level(logging.WARNING),
        ):
            base._enforce_readonly_src(wt_path)

        # mount must NOT be invoked on macOS.
        assert run_mount.call_count == 0
        # chmod 0500 was applied (we read back the mode).
        mode = (src_dir / "foo.py").stat().st_mode & 0o777
        assert mode == 0o500, f"expected 0o500, got {oct(mode)}"
        # WARNING was logged.
        assert any("policy-only" in r.message for r in caplog.records)

    def test_cleanup_reverses_readonly_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """remove_worktree reverses the read-only state (Linux path).

        On Linux the cleanup invokes ``umount`` for the worktree's
        src/ mount. On macOS no umount is needed (chmod is reversible
        by simply deleting the directory tree).
        """
        monkeypatch.setattr(base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(base.sys, "platform", "linux")
        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True)

        with (
            mock.patch.object(base, "_run_git", return_value=mock.Mock(returncode=0)),
            mock.patch.object(base, "_run_umount") as run_umount,
        ):
            base._cleanup_readonly_src(wt_path)

        assert run_umount.call_count >= 1
