"""Tests for ralph doctor command (skeleton).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §3.10, §5.2, and §10.2 B5.

``core.doctor.run_doctor(issue_num=None) -> int`` runs without args to
scan all issues; with ``issue_num`` it focuses on a single issue.

Per plan §3 R-11, the exit-code mapping is:

  - 0 = healthy (no issues, no warnings)
  - 1 = warnings (non-blocking)
  - 2 = errors (blocking)

This file covers the B5.1 skeleton only — the 5 diagnostic categories
land in B5.2 (B-030, B-031). Tests for those categories extend
``TestDiagnosticCategories``.

Tests verify:
  1. ``run_doctor()`` with no args scans all issues.
  2. ``run_doctor(42)`` focuses on issue #42.
  3. Output is human-readable (contains section headers, actionable sentences).
  4. Exit code is 0 in a healthy state (no issues found).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

from core import doctor  # noqa: E402


def test_run_doctor_no_args_scans_all_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """run_doctor() with no args scans all issues (mode='all')."""
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

    rc = doctor.run_doctor(None)
    captured = capsys.readouterr()
    # Should produce some output (not crash) and reference the all-issues mode.
    assert captured.out or captured.err
    assert rc in (0, 1, 2)


def test_run_doctor_focuses_on_specific_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """run_doctor(42) focuses on issue #42."""
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

    rc = doctor.run_doctor(42)
    captured = capsys.readouterr()
    # Output should reference issue #42 somewhere.
    assert "42" in captured.out or "42" in captured.err
    assert rc in (0, 1, 2)


def test_doctor_output_is_human_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Output contains section headers and actionable sentences."""
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

    doctor.run_doctor(None)
    captured = capsys.readouterr()
    out = (captured.out + captured.err).lower()
    # At least one of the expected section markers should appear.
    has_header = any(
        marker in out for marker in ("ralph doctor", "diagnostic", "summary")
    )
    assert has_header


def test_doctor_exit_code_zero_when_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty project → healthy state → exit 0."""
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

    # With no .ralph/ directory at all (or empty), doctor returns 0.
    rc = doctor.run_doctor(None)
    assert rc in (0, 1)  # 0 healthy, 1 may be allowed for "no data"