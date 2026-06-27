"""
Unit tests for core/validate.py collision handling.
"""

import sys
from pathlib import Path
from unittest import mock

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

import validate


def test_detect_collisions_no_collision():
    paths = [
        "tests/unit/test_cli.py",
        "tests/unit/test_engine.py",
        "tests/integration/test_cli_integration.py",
    ]
    assert validate.detect_collisions(paths) == {}


def test_detect_collisions_finds_collision():
    paths = [
        "tests/unit/test_cli.py",
        "tests/integration/test_cli.py",
    ]
    collisions = validate.detect_collisions(paths)
    assert collisions == {
        "test_cli.py": [
            "tests/unit/test_cli.py",
            "tests/integration/test_cli.py",
        ]
    }


def test_detect_collisions_multiple_collisions():
    paths = [
        "tests/unit/test_cli.py",
        "tests/integration/test_cli.py",
        "tests/unit/test_engine.py",
        "tests/integration/test_engine.py",
    ]
    collisions = validate.detect_collisions(paths)
    assert set(collisions.keys()) == {"test_cli.py", "test_engine.py"}
    assert sorted(collisions["test_cli.py"]) == sorted(
        ["tests/unit/test_cli.py", "tests/integration/test_cli.py"]
    )


def test_run_pytest_split_by_directory_runs_per_directory():
    """Verify paths are grouped by parent directory and pytest is invoked per group."""
    calls = []

    def fake_invocation(cmd, env=None):
        calls.append((cmd, env))
        return 0

    with mock.patch.object(validate, "run_pytest_invocation", fake_invocation):
        exit_code = validate.run_pytest_split_by_directory(
            base=["python", "-m", "pytest"],
            paths=[
                "tests/unit/test_cli.py",
                "tests/unit/test_engine.py",
                "tests/integration/test_cli.py",
            ],
            suffix=["-q"],
            env={"RALPH_NO_RECURSIVE_PYTEST": "1"},
        )

    assert exit_code == 0
    assert len(calls) == 2

    # One invocation for unit/, one for integration/.
    dirs_invoked = {tuple(cmd) for cmd, _ in calls}
    assert (
        "python",
        "-m",
        "pytest",
        "tests/unit/test_cli.py",
        "tests/unit/test_engine.py",
        "-q",
    ) in dirs_invoked
    assert (
        "python",
        "-m",
        "pytest",
        "tests/integration/test_cli.py",
        "-q",
    ) in dirs_invoked


def test_run_pytest_split_by_directory_returns_worst_exit_code():
    def fake_invocation(cmd, env=None):
        # Return 1 for unit, 0 for integration (alphabetical order)
        if any("unit" in part for part in cmd):
            return 1
        return 0

    with mock.patch.object(validate, "run_pytest_invocation", fake_invocation):
        exit_code = validate.run_pytest_split_by_directory(
            base=["python", "-m", "pytest"],
            paths=[
                "tests/integration/test_cli.py",
                "tests/unit/test_cli.py",
            ],
            suffix=["-q"],
        )

    assert exit_code == 1


def test_run_pytest_with_colliding_paths_splits_invocations(tmp_path, monkeypatch):
    """
    End-to-end check: two test files with the same basename in different
    directories are executed via separate pytest invocations and both pass.
    """
    unit_dir = tmp_path / "tests" / "unit"
    integration_dir = tmp_path / "tests" / "integration"
    unit_dir.mkdir(parents=True)
    integration_dir.mkdir(parents=True)

    (unit_dir / "test_cli.py").write_text(
        "def test_unit():\n    assert True\n", encoding="utf-8"
    )
    (integration_dir / "test_cli.py").write_text(
        "def test_integration():\n    assert True\n", encoding="utf-8"
    )

    # Force validate.py to use the temp project root and python.
    monkeypatch.setattr(validate, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(validate, "PYTHON_CMD", sys.executable)
    monkeypatch.setattr(validate, "PYTEST_ADOPTS", [])

    paths = [
        str(unit_dir / "test_cli.py"),
        str(integration_dir / "test_cli.py"),
    ]
    exit_code = validate.run_pytest("targeted", pytest_paths=paths)

    assert exit_code == 0


# ─────────────────────────────────────────────────────────
# A1.1 — PytestExitCodeClassifier (spec §10.1 A1)
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

    def test_unknown_exit_code_is_block(self) -> None:
        """Unknown exit codes (e.g., 99) → unknown / block."""
        result = validate.classify_pytest_exit_code(99)
        assert result.classification == "unknown"
        assert result.action == "block"

    def test_result_contains_exit_code(self) -> None:
        """The returned Classification carries the original exit_code field."""
        result = validate.classify_pytest_exit_code(1)
        assert result.exit_code == 1
