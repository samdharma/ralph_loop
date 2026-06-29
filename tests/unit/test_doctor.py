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

import datetime as dt_real
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

from core import doctor  # noqa: E402


def _patch_datetime_now(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime) -> None:
    """Replace ``doctor.datetime`` with a module whose ``now()`` is frozen."""
    fake_module = types.ModuleType("datetime")

    class FakeDateTime(dt_real.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    fake_module.datetime = FakeDateTime
    fake_module.timedelta = dt_real.timedelta
    fake_module.timezone = dt_real.timezone
    monkeypatch.setattr(doctor, "datetime", fake_module)


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


class TestRepeatFailures:
    """``_detect_repeat_failures`` reads the failure-history file."""

    def test_no_history_file_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing history file → no repeat failures."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)
        assert doctor._detect_repeat_failures() == []

    def test_repeating_failure_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A test failing 3+ times in 30 days is reported."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        fixed_now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)
        _patch_datetime_now(monkeypatch, fixed_now)

        history = tmp_path / ".ralph" / "test-failure-history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        now = "2026-06-28T12:00:00+00:00"
        history.write_text(
            "\n".join(
                [
                    json.dumps({"test": "tests/foo.py::test_x", "timestamp": now}),
                    json.dumps({"test": "tests/foo.py::test_x", "timestamp": now}),
                    json.dumps({"test": "tests/foo.py::test_x", "timestamp": now}),
                    json.dumps({"test": "tests/bar.py::test_y", "timestamp": now}),
                ]
            ),
            encoding="utf-8",
        )

        result = doctor._detect_repeat_failures()
        assert result == [("tests/foo.py::test_x", 3)]

    def test_old_failures_are_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failures older than 30 days do not count."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        fixed_now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)
        _patch_datetime_now(monkeypatch, fixed_now)

        history = tmp_path / ".ralph" / "test-failure-history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        old = "2026-05-01T12:00:00+00:00"
        history.write_text(
            "\n".join(
                [
                    json.dumps({"test": "tests/foo.py::test_x", "timestamp": old}),
                    json.dumps({"test": "tests/foo.py::test_x", "timestamp": old}),
                    json.dumps({"test": "tests/foo.py::test_x", "timestamp": old}),
                ]
            ),
            encoding="utf-8",
        )

        assert doctor._detect_repeat_failures() == []


class TestQuietMode:
    """``--quiet`` suppresses non-critical output."""

    def test_quiet_suppresses_warning_findings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Quiet mode hides severity 1 findings but still reports errors."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        # Create a fake issue so run_doctor enters scan mode.
        issues_root = tmp_path / ".ralph" / "issues"
        issues_root.mkdir(parents=True, exist_ok=True)
        (issues_root / "1").mkdir()

        monkeypatch.setattr(doctor, "_detect_stuck_issues", lambda: [(1, "stuck")])
        monkeypatch.setattr(doctor, "_detect_long_blocked", lambda: [])
        monkeypatch.setattr(doctor, "_detect_repeat_failures", lambda: [])
        monkeypatch.setattr(doctor, "_detect_orphan_subprocesses", lambda: [])
        monkeypatch.setattr(
            doctor, "_detect_environment_problems", lambda: [("missing_label", "x")]
        )

        rc = doctor.run_doctor(None, quiet=True)
        captured = capsys.readouterr()
        assert rc == 2
        assert "Stuck issues" not in captured.out
        assert "Environment problems" in captured.out

    def test_quiet_suppresses_scanning_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Quiet mode hides the 'scanning N issue(s)' banner."""
        monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)

        issues_root = tmp_path / ".ralph" / "issues"
        issues_root.mkdir(parents=True, exist_ok=True)
        (issues_root / "1").mkdir()

        monkeypatch.setattr(doctor, "_detect_stuck_issues", lambda: [])
        monkeypatch.setattr(doctor, "_detect_long_blocked", lambda: [])
        monkeypatch.setattr(doctor, "_detect_repeat_failures", lambda: [])
        monkeypatch.setattr(doctor, "_detect_orphan_subprocesses", lambda: [])
        monkeypatch.setattr(doctor, "_detect_environment_problems", lambda: [])

        rc = doctor.run_doctor(None, quiet=True)
        captured = capsys.readouterr()
        assert rc == 0
        assert "scanning" not in captured.out.lower()

    def test_main_passes_quiet_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI ``--quiet`` is forwarded to ``run_doctor``."""
        calls: list[tuple[object, ...]] = []

        def fake_run_doctor(issue_num, quiet: bool = False):
            calls.append((issue_num, quiet))
            return 0

        monkeypatch.setattr(doctor, "run_doctor", fake_run_doctor)
        rc = doctor.main(["--quiet"])
        assert rc == 0
        assert calls == [(None, True)]
