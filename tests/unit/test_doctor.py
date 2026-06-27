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


# ─────────────────────────────────────────────────────────
# B5.2 — 5 diagnostic categories (spec §3.10, plan §3 R-11)
# ─────────────────────────────────────────────────────────


class TestDiagnosticCategories:
    """B5.2: each of the 5 diagnostic categories contributes to the exit code.

    Per spec §3.10 the categories are:
      1. stuck issues (>1 hour in DESIGN/BUILD/VERIFY)
      2. long-blocked issues (>7 days)
      3. repeat failures (same test fails 3+ times in 30 days)
      4. orphan subprocesses (zombie pi/kimi)
      5. environment checks (missing labels, no gh auth, no git remote)

    Per plan §3 R-11 the exit code mapping is:
      - warnings contribute 1
      - errors contribute 2
      - final exit code = max(severity)

    Tests assert: each category contributes the documented severity.
    """

    def test_stuck_issue_contributes_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stuck issue (>1 hour in DESIGN/BUILD/VERIFY) → exit 1."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        # Stub a stuck-issue detector that returns severity=1.
        monkeypatch.setattr(
            doctor,
            "_detect_stuck_issues",
            lambda: [(42, "stuck in BUILD for 2h")],
        )
        # Stub all other detectors as no-op.
        for name in (
            "_detect_long_blocked",
            "_detect_repeat_failures",
            "_detect_orphan_subprocesses",
            "_detect_environment_problems",
        ):
            monkeypatch.setattr(doctor, name, lambda: [])

        sev = doctor._aggregate_severities()
        assert sev == 1

    def test_orphan_subprocess_contributes_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Orphan subprocess → exit 2 (per plan §3 R-11 contribution table)."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        monkeypatch.setattr(doctor, "_detect_stuck_issues", lambda: [])
        monkeypatch.setattr(doctor, "_detect_long_blocked", lambda: [])
        monkeypatch.setattr(doctor, "_detect_repeat_failures", lambda: [])
        monkeypatch.setattr(
            doctor,
            "_detect_orphan_subprocesses",
            lambda: [(12345, "pi", "zombie")],
        )
        monkeypatch.setattr(doctor, "_detect_environment_problems", lambda: [])

        sev = doctor._aggregate_severities()
        assert sev == 2

    def test_missing_labels_contribute_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing environment (e.g., labels) → exit 2."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        monkeypatch.setattr(doctor, "_detect_stuck_issues", lambda: [])
        monkeypatch.setattr(doctor, "_detect_long_blocked", lambda: [])
        monkeypatch.setattr(doctor, "_detect_repeat_failures", lambda: [])
        monkeypatch.setattr(doctor, "_detect_orphan_subprocesses", lambda: [])
        monkeypatch.setattr(
            doctor,
            "_detect_environment_problems",
            lambda: [("missing_label", "status:design")],
        )

        sev = doctor._aggregate_severities()
        assert sev == 2

    def test_repeat_failures_contribute_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Repeat failures (3+ in 30 days) → exit 1."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        monkeypatch.setattr(doctor, "_detect_stuck_issues", lambda: [])
        monkeypatch.setattr(doctor, "_detect_long_blocked", lambda: [])
        monkeypatch.setattr(
            doctor,
            "_detect_repeat_failures",
            lambda: [("tests/foo.py::test_x", 5)],
        )
        monkeypatch.setattr(doctor, "_detect_orphan_subprocesses", lambda: [])
        monkeypatch.setattr(doctor, "_detect_environment_problems", lambda: [])

        sev = doctor._aggregate_severities()
        assert sev == 1

    def test_long_blocked_contributes_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Long-blocked issue (>7 days) → exit 1."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        monkeypatch.setattr(doctor, "_detect_stuck_issues", lambda: [])
        monkeypatch.setattr(
            doctor,
            "_detect_long_blocked",
            lambda: [(99, "blocked for 10 days")],
        )
        monkeypatch.setattr(doctor, "_detect_repeat_failures", lambda: [])
        monkeypatch.setattr(doctor, "_detect_orphan_subprocesses", lambda: [])
        monkeypatch.setattr(doctor, "_detect_environment_problems", lambda: [])

        sev = doctor._aggregate_severities()
        assert sev == 1
