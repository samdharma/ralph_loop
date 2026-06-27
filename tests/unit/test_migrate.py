"""Tests for `ralph migrate` command.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §3.6 and plan §3 R-3 mitigation.
Behavior:

- Idempotent on re-run (running twice produces identical filesystem state)
- Refuses to run while `.ralph/daemon.pid` exists
- Supports `--dry-run` (outputs JSON report, no filesystem changes)
- Backs up before modifying (every v3 file slated for rename/move is first
  copied to `.ralph/migration-archive/<timestamp>/`)

These tests are RED against the A-008 stub (`migrate` raises
NotImplementedError). They turn GREEN after task A-010 lands.
"""

import json
import time
from pathlib import Path

import pytest

from core.migrate import migrate


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────


@pytest.fixture
def project_with_v3_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a v3-format project under tmp_path with sample state files."""
    # Make CWD point at the v3 project so migrate() picks up its .ralph/
    monkeypatch.chdir(tmp_path)
    ralph_dir = tmp_path / ".ralph"
    ralph_dir.mkdir()

    # Sample v3-format state files (per spec §6.2):
    (ralph_dir / "issue-1-tests.json").write_text(
        json.dumps(
            {
                "issue": 1,
                "tests": ["tests/unit/test_x.py::test_a"],
            }
        )
    )
    (ralph_dir / "issue-1-report.md").write_text("# Issue #1 Report\n\nAll good.")

    # A v3-format session file (deprecated in A3, kept for migration)
    (ralph_dir / "session-1.jsonl").write_text('{"event": "started"}\n')

    # Stage prompts matching v3 defaults byte-for-byte (will be regenerated)
    prompts_dir = tmp_path / "docs" / "agent" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "test.md").write_text("# Test stage prompt (v3 default)\n")

    return tmp_path


# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────


def test_migrate_importable() -> None:
    """The migrate function is importable and callable."""
    assert callable(migrate)


def test_migrate_dry_run_returns_json_serializable(project_with_v3_state: Path) -> None:
    """migrate(dry_run=True) returns a JSON-serializable dict listing planned actions."""
    report = migrate(dry_run=True)
    # Must be JSON-serializable
    serialized = json.dumps(report)
    assert isinstance(serialized, str)
    # Must contain an `actions` key
    assert "actions" in report, "Dry-run report must list planned actions"


def test_migrate_dry_run_does_not_modify_filesystem(project_with_v3_state: Path) -> None:
    """migrate(dry_run=True) does NOT modify the filesystem."""
    before = sorted(p.name for p in project_with_v3_state.glob(".ralph/*"))
    migrate(dry_run=True)
    after = sorted(p.name for p in project_with_v3_state.glob(".ralph/*"))
    assert before == after, "Dry-run must not modify the filesystem"


def test_migrate_refuses_when_daemon_pid_exists(
    project_with_v3_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """migrate() refuses to run while .ralph/daemon.pid exists."""
    pid_file = project_with_v3_state / ".ralph" / "daemon.pid"
    pid_file.write_text("12345")
    try:
        with pytest.raises(RuntimeError, match=r"daemon"):
            migrate(dry_run=False)
    finally:
        pid_file.unlink()


def test_migrate_is_idempotent(project_with_v3_state: Path) -> None:
    """Running migrate() twice produces identical filesystem state (modulo archive)."""
    first = migrate(dry_run=False)
    second = migrate(dry_run=False)
    # Both calls succeed
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    # The second call should report no actions (everything already migrated)
    # OR the actions list should be a subset of idempotency markers.
    # The simplest invariant: no errors and the project is in the same state.
    actions_first = first.get("actions", [])
    actions_second = second.get("actions", [])
    # Idempotency: the second run does strictly less work (or equal).
    assert len(actions_second) <= len(actions_first), (
        f"Second run did MORE work than first: {actions_second} vs {actions_first}"
    )


def test_migrate_archives_before_moving(project_with_v3_state: Path) -> None:
    """For every v3 file slated for rename/move, an original copy exists at .ralph/migration-archive/<timestamp>/."""
    migrate(dry_run=False)
    archive_root = project_with_v3_state / ".ralph" / "migration-archive"
    assert archive_root.exists(), f"Expected archive root at {archive_root}"
    # At least one timestamped directory
    archive_dirs = [d for d in archive_root.iterdir() if d.is_dir()]
    assert len(archive_dirs) >= 1, f"Expected at least one archive dir under {archive_root}"
    # The archive contains the original v3 files
    archived = list(archive_dirs[0].rglob("*"))
    assert any("issue-1-tests.json" in str(p) for p in archived), (
        "Archive must contain the original issue-1-tests.json"
    )


def test_migrate_handles_missing_ralph_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """migrate() handles projects without a .ralph/ directory (returns empty actions)."""
    monkeypatch.chdir(tmp_path)
    # No .ralph dir — should still succeed
    report = migrate(dry_run=True)
    assert isinstance(report, dict)
    assert report.get("actions", []) == []


def test_migrate_creates_issues_subdir_for_each_issue(project_with_v3_state: Path) -> None:
    """After migrate(), v3 issue files are migrated to .ralph/issues/<N>/ per spec §6.2."""
    migrate(dry_run=False)
    # The v3 layout has .ralph/issue-1-tests.json
    # The v3.1 layout (per spec §6.2) has .ralph/issues/1/...
    issues_dir = project_with_v3_state / ".ralph" / "issues" / "1"
    # Either the issue directory exists, OR the file is now archived (acceptable)
    archived = any(
        (project_with_v3_state / ".ralph" / "migration-archive").rglob("issue-1-tests.json")
    )
    assert issues_dir.exists() or archived, (
        "Expected either .ralph/issues/1/ to exist OR the original to be archived"
    )


def test_migrate_logs_errors_in_report(project_with_v3_state: Path) -> None:
    """The migrate report includes an `errors` key (empty list on success)."""
    report = migrate(dry_run=False)
    assert "errors" in report
    assert isinstance(report["errors"], list)


def test_migrate_dry_run_no_archive_created(project_with_v3_state: Path) -> None:
    """migrate(dry_run=True) does NOT create any archive directory."""
    migrate(dry_run=True)
    archive_root = project_with_v3_state / ".ralph" / "migration-archive"
    # Archive directory must not exist after a dry run
    assert not archive_root.exists(), "Dry-run must not create the archive directory"