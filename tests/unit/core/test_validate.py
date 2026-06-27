"""Unit tests for core/validate.py — A1 (exit-code classification), A4 (JUnit XML), A6 (critical paths).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §10.1 A1/A4/A6.

These tests cover the NEW functionality added in Phase A:
- A1.1: classify_pytest_exit_code() (PytestExitCodeClassifier)
- A1.2: run_pytest_invocation() returning a structured dict
- A4.1: --junitxml flag emitting JUnit XML
- A6.1: [validate] critical_paths config + --critical flag

Pre-existing tests for collision handling live at tests/unit/test_validate.py
and are not duplicated here.
"""

import sys
from pathlib import Path
from unittest import mock

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "core"))

import validate  # noqa: E402


# ─────────────────────────────────────────────────────────
# A1.1 — PytestExitCodeClassifier
# ─────────────────────────────────────────────────────────


class TestPytestExitCodeClassifier:
    """A1.1: classify_pytest_exit_code(exit_code) → Classification per spec §10.1 A1."""

    def test_exit_zero_is_success(self) -> None:
        """Exit 0 → success / accept."""
        result = validate.classify_pytest_exit_code(0)
        assert result.action == "accept"
        assert result.classification == "success"

    def test_exit_one_is_test_failure_block(self) -> None:
        """Exit 1 → test_failure / block."""
        result = validate.classify_pytest_exit_code(1)
        assert result.action == "block"
        assert result.classification == "test_failure"

    def test_exit_124_is_timeout_retry_transient(self) -> None:
        """Exit 124 → timeout / retry_transient."""
        result = validate.classify_pytest_exit_code(124)
        assert result.classification == "timeout"
        assert result.action == "retry_transient"

    def test_exit_137_is_interrupted_retry_transient(self) -> None:
        """Exit 137 → interrupted / retry_transient (distinct from timeout)."""
        result = validate.classify_pytest_exit_code(137)
        assert result.classification == "interrupted"
        assert result.action == "retry_transient"

    def test_exit_143_is_interrupted_retry_transient(self) -> None:
        """Exit 143 → interrupted / retry_transient (distinct from timeout)."""
        result = validate.classify_pytest_exit_code(143)
        assert result.classification == "interrupted"
        assert result.action == "retry_transient"

    def test_interrupted_distinct_from_timeout(self) -> None:
        """137 and 143 must be 'interrupted', NOT 'timeout' (spec §10.1 A1)."""
        c137 = validate.classify_pytest_exit_code(137)
        c143 = validate.classify_pytest_exit_code(143)
        c124 = validate.classify_pytest_exit_code(124)
        assert c137.classification != c124.classification
        assert c143.classification != c124.classification

    def test_unknown_exit_code_is_internal_error(self) -> None:
        """Unknown exit codes (e.g., 99) → internal_error / block."""
        result = validate.classify_pytest_exit_code(99)
        assert result.classification == "internal_error"
        assert result.action == "block"

    def test_result_contains_exit_code(self) -> None:
        """The returned Classification carries the original exit_code field."""
        result = validate.classify_pytest_exit_code(1)
        assert result.exit_code == 1