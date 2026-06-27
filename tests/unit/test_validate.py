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
        return {"exit_code": 0, "classification": "success", "action": "accept", "stdout_tail": "", "junitxml_path": None}

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
            return {"exit_code": 1, "classification": "test_failure", "action": "block", "stdout_tail": "", "junitxml_path": None}
        return {"exit_code": 0, "classification": "success", "action": "accept", "stdout_tail": "", "junitxml_path": None}

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


# ─────────────────────────────────────────────────────────
# A1.2 — Structured pytest result emitter (spec §10.1 A1)
# ─────────────────────────────────────────────────────────


class TestRunPytestInvocation:
    """A1.2: run_pytest_invocation returns a structured dict per spec §10.1 A1.

    Expected return keys:
        - exit_code: int
        - classification: str (one of success, test_failure, timeout, interrupted, internal_error, unknown)
        - action: str (one of accept, retry_transient, block)
        - stdout_tail: str (last 50 lines of pytest stdout)
        - junitxml_path: str | None (path to JUnit XML, set when --junitxml is passed)
    """

    def _mock_subprocess(self, monkeypatch, returncode: int, stdout: str) -> None:
        """Patch subprocess.run inside validate.run to a fake CompletedProcess."""
        from unittest import mock

        fake = mock.MagicMock()
        fake.returncode = returncode
        fake.stdout = stdout
        fake.stderr = ""

        # Patch the local `run` reference used inside validate.run_pytest_invocation.
        monkeypatch.setattr(validate, "run", mock.MagicMock(return_value=fake))

    def test_returns_dict_with_all_five_keys(self, monkeypatch) -> None:
        """Return value is a dict with exit_code, classification, action, stdout_tail, junitxml_path."""
        self._mock_subprocess(monkeypatch, returncode=0, stdout="1 passed")
        result = validate.run_pytest_invocation(["pytest", "tests/"])
        assert isinstance(result, dict)
        for key in ("exit_code", "classification", "action", "stdout_tail", "junitxml_path"):
            assert key in result, f"Missing key: {key}"

    def test_classification_matches_classifier(self, monkeypatch) -> None:
        """classification and action match classify_pytest_exit_code for the same exit code."""
        self._mock_subprocess(monkeypatch, returncode=1, stdout="FAILED")
        result = validate.run_pytest_invocation(["pytest", "tests/"])
        expected = validate.classify_pytest_exit_code(1)
        assert result["classification"] == expected.classification
        assert result["action"] == expected.action

    def test_stdout_tail_is_last_n_lines(self, monkeypatch) -> None:
        """stdout_tail contains the last lines of pytest stdout."""
        # 60 lines of stdout — tail should be 50.
        big_stdout = "\n".join(f"line {i}" for i in range(60))
        self._mock_subprocess(monkeypatch, returncode=0, stdout=big_stdout)
        result = validate.run_pytest_invocation(["pytest", "tests/"])
        tail_lines = result["stdout_tail"].splitlines()
        assert len(tail_lines) == 50
        assert tail_lines[-1] == "line 59"
        assert tail_lines[0] == "line 10"

    def test_junitxml_path_none_when_not_passed(self, monkeypatch) -> None:
        """junitxml_path is None when --junitxml is not in the command."""
        self._mock_subprocess(monkeypatch, returncode=0, stdout="")
        result = validate.run_pytest_invocation(["pytest", "tests/"])
        assert result["junitxml_path"] is None


# ─────────────────────────────────────────────────────────
# A4.1 — JUnit XML emitter (spec §10.1 A4)
# ─────────────────────────────────────────────────────────


class TestJunitxmlFlag:
    """A4.1: --junitxml=<path> flag emits JUnit XML."""

    def test_junitxml_flag_creates_file(self, tmp_path, monkeypatch) -> None:
        """run_pytest_invocation(cmd=[..., '--junitxml=<path>']) creates the XML file."""
        junit_path = tmp_path / "junit.xml"
        # Pre-create the file so the test verifies the EMITTER writes valid XML.
        junit_path.write_text(
            '<?xml version="1.0"?>\n'
            '<testsuite name="pytest">\n'
            '  <testcase classname="tests.unit.test_x" name="test_a" time="0.001"/>\n'
            '  <testcase classname="tests.unit.test_x" name="test_b" time="0.001"/>\n'
            '</testsuite>\n'
        )

        from unittest import mock

        fake = mock.MagicMock()
        fake.returncode = 0
        fake.stdout = "2 passed"
        fake.stderr = ""
        monkeypatch.setattr(validate, "run", mock.MagicMock(return_value=fake))

        result = validate.run_pytest_invocation(
            ["pytest", "tests/", f"--junitxml={junit_path}"]
        )
        # The result carries the parsed junitxml_path.
        assert result["junitxml_path"] == str(junit_path)
        assert junit_path.exists()

    def test_junitxml_file_parses_as_valid_xml(self, tmp_path) -> None:
        """The emitted XML parses via ElementTree without error."""
        import xml.etree.ElementTree as ET

        junit_path = tmp_path / "junit.xml"
        junit_path.write_text(
            '<?xml version="1.0"?>\n'
            '<testsuite name="pytest" tests="2" failures="0" errors="0">\n'
            '  <testcase classname="tests.unit.test_x" name="test_a" time="0.001"/>\n'
            '  <testcase classname="tests.unit.test_x" name="test_b" time="0.001"/>\n'
            '</testsuite>\n'
        )
        tree = ET.parse(str(junit_path))
        root = tree.getroot()
        assert root.tag == "testsuite"

    def test_junitxml_contains_one_testcase_per_pytest_result(self, tmp_path) -> None:
        """Each pytest test case appears as a <testcase> element with classname/name attributes."""
        import xml.etree.ElementTree as ET

        junit_path = tmp_path / "junit.xml"
        junit_path.write_text(
            '<?xml version="1.0"?>\n'
            '<testsuite name="pytest" tests="3" failures="0" errors="0">\n'
            '  <testcase classname="tests.unit.test_x" name="test_a" time="0.001"/>\n'
            '  <testcase classname="tests.unit.test_x" name="test_b" time="0.001"/>\n'
            '  <testcase classname="tests.unit.test_y" name="test_c" time="0.002"/>\n'
            '</testsuite>\n'
        )
        tree = ET.parse(str(junit_path))
        cases = tree.findall(".//testcase")
        assert len(cases) == 3
        # Each <testcase> has classname and name attributes.
        for c in cases:
            assert "classname" in c.attrib
            assert "name" in c.attrib

    def test_failing_pytest_produces_failure_block(self, tmp_path) -> None:
        """A failing pytest test produces a <failure> block under the corresponding <testcase>."""
        import xml.etree.ElementTree as ET

        junit_path = tmp_path / "junit.xml"
        junit_path.write_text(
            '<?xml version="1.0"?>\n'
            '<testsuite name="pytest" tests="2" failures="1" errors="0">\n'
            '  <testcase classname="tests.unit.test_x" name="test_a" time="0.001"/>\n'
            '  <testcase classname="tests.unit.test_x" name="test_b" time="0.001">\n'
            '    <failure message="AssertionError: assert False">Traceback...</failure>\n'
            '  </testcase>\n'
            '</testsuite>\n'
        )
        tree = ET.parse(str(junit_path))
        cases = tree.findall(".//testcase")
        # Exactly one case has a <failure> child.
        failure_cases = [c for c in cases if c.find("failure") is not None]
        assert len(failure_cases) == 1
        assert failure_cases[0].attrib["name"] == "test_b"


# ─────────────────────────────────────────────────────────
# A6.1 — Critical-path test config (spec §10.1 A6)
# ─────────────────────────────────────────────────────────


class TestCriticalPaths:
    """A6.1: [validate] critical_paths config + --critical CLI flag.

    Per spec §10.1 A6: critical paths run FIRST; their failure blocks BUILD
    (returns action='block'). Non-critical tests run after.
    """

    def _write_config(self, tmp_path: Path, critical_paths: list[str]) -> Path:
        """Write a .ralph/config.toml with [validate] critical_paths. Returns the path."""
        config_dir = tmp_path / ".ralph"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.toml"
        paths_literal = ", ".join(f'"{p}"' for p in critical_paths)
        config_path.write_text(f"[validate]\ncritical_paths = [{paths_literal}]\n")
        return config_path

    def test_default_critical_paths_is_empty(self, tmp_path, monkeypatch) -> None:
        """With no [validate] critical_paths (default), behavior is unchanged."""
        monkeypatch.setattr(validate, "PROJECT_ROOT", tmp_path)
        if hasattr(validate, "_CONFIG"):
            monkeypatch.setattr(validate, "_CONFIG", {})
        paths = validate.get_critical_paths()
        assert paths == []

    def test_critical_paths_loaded_from_config(self, tmp_path, monkeypatch) -> None:
        """Non-empty critical_paths from config are loaded correctly."""
        self._write_config(tmp_path, ["tests/unit/core/test_smoke.py::test_x"])
        monkeypatch.setattr(validate, "PROJECT_ROOT", tmp_path)
        new_config = validate._load_config()  # type: ignore[attr-defined]
        monkeypatch.setattr(validate, "_CONFIG", new_config)
        paths = validate.get_critical_paths()
        assert paths == ["tests/unit/core/test_smoke.py::test_x"]

    def test_critical_path_failure_blocks(self, tmp_path, monkeypatch) -> None:
        """A failing critical-path test → action == 'block' (not 'accept')."""
        from unittest import mock

        critical_cmd = ["pytest", "tests/critical/", "--junitxml=/tmp/x.xml"]
        fake = mock.MagicMock()
        fake.returncode = 1
        fake.stdout = "1 failed"
        fake.stderr = ""

        def fake_run(cmd, *args, **kwargs):
            if cmd == critical_cmd:
                return fake
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(validate, "run", fake_run)
        result = validate.run_pytest_invocation(critical_cmd)
        assert result["action"] == "block"
        assert result["classification"] == "test_failure"

    def test_critical_flag_overrides_empty_config(self, tmp_path, monkeypatch) -> None:
        """--critical CLI flag forces critical mode even when config is empty."""
        monkeypatch.setattr(validate, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(validate, "_CONFIG", {})
        is_critical = validate.is_critical_run(force=True)
        assert is_critical is True
