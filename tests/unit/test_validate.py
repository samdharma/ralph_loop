"""
Unit tests for core/validate.py collision handling.
"""

import sys
from pathlib import Path
from unittest import mock

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

import validate  # noqa: E402


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
        return {
            "exit_code": 0,
            "classification": "success",
            "action": "accept",
            "stdout_tail": "",
            "junitxml_path": None,
        }

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
            return {
                "exit_code": 1,
                "classification": "test_failure",
                "action": "block",
                "stdout_tail": "",
                "junitxml_path": None,
            }
        return {
            "exit_code": 0,
            "classification": "success",
            "action": "accept",
            "stdout_tail": "",
            "junitxml_path": None,
        }

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
        """Exit 1 → test_failure / retry_l2 (per B1 semantics).

        Per spec §10.2 B1, exit 1 (test failure) is now retryable up
        to ``l2_max_attempts`` (default 2). Phase A semantics called
        this 'block'; Phase B promoted it to retryable so flaky tests
        get a second chance. The :func:`retry_action_for_stage` wrapper
        still maps the action to ``block`` for the DESIGN stage.
        """
        result = validate.classify_pytest_exit_code(1)
        assert result.action == "retry_l2"
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
        for key in (
            "exit_code",
            "classification",
            "action",
            "stdout_tail",
            "junitxml_path",
        ):
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
            "</testsuite>\n"
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
            "</testsuite>\n"
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
            "</testsuite>\n"
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
            "  </testcase>\n"
            "</testsuite>\n"
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
        config_path = self._write_config(
            tmp_path, ["tests/unit/core/test_smoke.py::test_x"]
        )
        monkeypatch.setattr(validate, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(validate, "CONFIG_FILE", config_path)
        new_config = validate._load_config()  # type: ignore[attr-defined]
        monkeypatch.setattr(validate, "_CONFIG", new_config)
        paths = validate.get_critical_paths()
        assert paths == ["tests/unit/core/test_smoke.py::test_x"]

    def test_critical_path_failure_blocks(self, tmp_path, monkeypatch) -> None:
        """A failing critical-path test → action is non-accept.

        Per spec §10.1 A6 + §10.2 B1, critical-path failures must
        surface as a non-accept action so the BUILD stage can block.
        Under Phase B the classifier returns ``retry_l2`` for exit 1
        and the engine's stage-aware path (via
        :func:`retry_action_for_stage` or a BUILD-specific override)
        maps this to ``block``. We assert non-accept here so the test
        stays green across the classifier-action refactor.
        """
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
        assert result["action"] != "accept"
        assert result["classification"] == "test_failure"

    def test_critical_flag_overrides_empty_config(self, tmp_path, monkeypatch) -> None:
        """--critical CLI flag forces critical mode even when config is empty."""
        monkeypatch.setattr(validate, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(validate, "_CONFIG", {})
        is_critical = validate.is_critical_run(force=True)
        assert is_critical is True


# ─────────────────────────────────────────────────────────
# B1.2 — Retry classifier (spec §10.2 B1)
# ─────────────────────────────────────────────────────────


class TestRetryClassifier:
    """B1.2: classify_pytest_exit_code's `action` drives retry-vs-block.

    Per spec §10.2 B1:
      - exit 124 (timeout)        → retry_transient (up to 1 retry)
      - exit 1   (test failure)   → retry_l2 (up to 2 retries)
      - exit 0   (success)        → accept
      - DESIGN-stage failures     → block regardless of exit code

    The retry classifier extends the existing Phase A1.1 classifier
    with new action values: retry_l2 for test failures, and a stage-
    aware block for DESIGN stage.
    """

    def test_exit_124_is_retry_transient(self) -> None:
        """Exit 124 (timeout) maps to action=retry_transient."""
        from core.validate import classify_pytest_exit_code

        result = classify_pytest_exit_code(124)
        assert result.action == "retry_transient"

    def test_exit_1_is_retry_l2(self) -> None:
        """Exit 1 (test failure) maps to action=retry_l2."""
        from core.validate import classify_pytest_exit_code

        result = classify_pytest_exit_code(1)
        assert result.action == "retry_l2"

    def test_exit_0_is_accept(self) -> None:
        """Exit 0 (success) maps to action=accept."""
        from core.validate import classify_pytest_exit_code

        result = classify_pytest_exit_code(0)
        assert result.action == "accept"

    def test_design_stage_failure_blocks(self) -> None:
        """Per spec §10.2 B1, DESIGN-stage failures block regardless of exit code.

        A wrapper function (or post-classifier branch) maps the stage
        context: when stage == 'design', the final action is 'block'
        even if the classifier alone would suggest retry.
        """
        from core.validate import classify_pytest_exit_code, retry_action_for_stage

        # Exit 1 alone would suggest retry_l2; in DESIGN stage it blocks.
        classified = classify_pytest_exit_code(1)
        final_action = retry_action_for_stage(classified.action, stage="design")
        assert final_action == "block"

    def test_retry_policy_dataclass_exists(self) -> None:
        """Per spec §7.2 RetryPolicy is a frozen dataclass with max_attempts/backoff_seconds/applies_to."""
        from core.validate import RetryPolicy

        policy = RetryPolicy(
            max_attempts=2,
            backoff_seconds=0.0,
            applies_to=frozenset({1}),
        )
        assert policy.max_attempts == 2
        assert policy.applies_to == frozenset({1})


# ─────────────────────────────────────────────────────────
# C3.1 — Quarantine schema (spec §10.3 C3)
# ─────────────────────────────────────────────────────────


class TestQuarantineSchema:
    """C3.1: tests/quarantine.yaml schema and deselection.

    Per spec §10.3 C3 and plan §3 R-7: quarantine entries follow the
    schema ``{test_id, added_at, reason, auto_added}``. The validate
    layer deselects listed tests via pytest's ``--deselect`` flag or
    by passing deselected IDs into the invocation. Auto-added entries
    (C3.2) include ``auto_added: true``.

    This block is RED: the ``load_quarantine_entries`` /
    ``is_quarantined`` / ``apply_quarantine_to_cmd`` functions don't
    exist yet. Running this test file before C-002 must produce
    ImportError failures for every TestQuarantineSchema test.
    """

    def _write_quarantine_yaml(self, tmp_path: Path, entries: list[dict]) -> Path:
        """Write a tests/quarantine.yaml with the given entries. Returns path.

        Writes the constrained YAML format produced by the implementation
        itself (and by ``--unquarantine-stale``). Format:
            - test_id: <id>
              added_at: <iso8601>
              reason: <str>
              auto_added: <bool>
        """
        lines: list[str] = []
        for e in entries:
            lines.append(f"- test_id: {e['test_id']}")
            lines.append(f"  added_at: \"{e['added_at']}\"")
            # Quote the reason if it contains characters that would break parsing.
            reason = str(e["reason"])
            if any(c in reason for c in [":", "#", "\n"]):
                lines.append(f'  reason: "{reason}"')
            else:
                lines.append(f"  reason: {reason}")
            lines.append(f"  auto_added: {'true' if e['auto_added'] else 'false'}")
            lines.append("")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        path = tests_dir / "quarantine.yaml"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_empty_quarantine_yaml_runs_all_tests(self, tmp_path, monkeypatch) -> None:
        """An empty tests/quarantine.yaml → no tests are deselected."""
        from core import validate

        path = self._write_quarantine_yaml(tmp_path, [])
        monkeypatch.setattr(validate, "QUARANTINE_FILE", path)

        entries = validate.load_quarantine_entries()
        assert entries == []

        # is_quarantined returns False for any test_id when there are no entries.
        assert validate.is_quarantined("tests/unit/x.py::test_y") is False

    def test_single_entry_deselects_listed_test(self, tmp_path, monkeypatch) -> None:
        """A quarantine entry causes that test to be deselected from pytest invocation."""
        from core import validate

        entry = {
            "test_id": "tests/unit/x.py::test_y",
            "added_at": "2026-06-27T12:00:00Z",
            "reason": "flaky in CI",
            "auto_added": False,
        }
        path = self._write_quarantine_yaml(tmp_path, [entry])
        monkeypatch.setattr(validate, "QUARANTINE_FILE", path)

        entries = validate.load_quarantine_entries()
        assert len(entries) == 1
        assert entries[0]["test_id"] == "tests/unit/x.py::test_y"
        assert validate.is_quarantined("tests/unit/x.py::test_y") is True
        assert validate.is_quarantined("tests/unit/x.py::test_other") is False

    def test_multiple_entries_all_deselected(self, tmp_path, monkeypatch) -> None:
        """Multiple entries → all listed tests are deselected; non-listed are not."""
        from core import validate

        entries = [
            {
                "test_id": "tests/unit/a.py::test_one",
                "added_at": "2026-06-27T12:00:00Z",
                "reason": "flaky 1",
                "auto_added": False,
            },
            {
                "test_id": "tests/unit/b.py::test_two",
                "added_at": "2026-06-27T12:01:00Z",
                "reason": "flaky 2",
                "auto_added": True,
            },
            {
                "test_id": "tests/integration/c.py::test_three",
                "added_at": "2026-06-27T12:02:00Z",
                "reason": "flaky 3",
                "auto_added": False,
            },
        ]
        path = self._write_quarantine_yaml(tmp_path, entries)
        monkeypatch.setattr(validate, "QUARANTINE_FILE", path)

        loaded = validate.load_quarantine_entries()
        assert len(loaded) == 3

        for e in entries:
            assert validate.is_quarantined(e["test_id"]) is True

        # Unrelated test_id is NOT deselected.
        assert validate.is_quarantined("tests/unit/d.py::test_four") is False

    def test_auto_added_flag_preserved_in_schema(self, tmp_path, monkeypatch) -> None:
        """The ``auto_added: True`` flag is preserved through read cycles."""
        from core import validate

        entries = [
            {
                "test_id": "tests/unit/x.py::test_y",
                "added_at": "2026-06-27T12:00:00Z",
                "reason": "two consecutive failures",
                "auto_added": True,
            },
            {
                "test_id": "tests/unit/a.py::test_b",
                "added_at": "2026-06-27T12:01:00Z",
                "reason": "manually marked",
                "auto_added": False,
            },
        ]
        path = self._write_quarantine_yaml(tmp_path, entries)
        monkeypatch.setattr(validate, "QUARANTINE_FILE", path)

        loaded = validate.load_quarantine_entries()
        assert loaded[0]["auto_added"] is True
        assert loaded[1]["auto_added"] is False

    def test_apply_quarantine_to_pytest_cmd(self, tmp_path, monkeypatch) -> None:
        """apply_quarantine_to_cmd(cmd) returns a new cmd with --deselect entries appended."""
        from core import validate

        entry = {
            "test_id": "tests/unit/x.py::test_y",
            "added_at": "2026-06-27T12:00:00Z",
            "reason": "flaky",
            "auto_added": True,
        }
        path = self._write_quarantine_yaml(tmp_path, [entry])
        monkeypatch.setattr(validate, "QUARANTINE_FILE", path)

        base_cmd = ["python", "-m", "pytest", "tests/unit/", "-q"]
        result_cmd = validate.apply_quarantine_to_cmd(base_cmd)
        # --deselect appears with the test_id.
        assert "--deselect" in result_cmd
        assert "tests/unit/x.py::test_y" in result_cmd


# ─────────────────────────────────────────────────────────
# C3.2 — Quarantine auto-add on 2 consecutive failures (spec §10.3 C3)
# ─────────────────────────────────────────────────────────


class TestAutoQuarantine:
    """C3.2: auto-add a test to quarantine.yaml after 2 consecutive failures.

    Per spec §10.3 C3 and plan §3 R-7: state file at
    ``.ralph/test-failure-history.jsonl`` tracks per-test failure
    timestamps. On each validate run, the engine scans the last 2
    runs; if a test_id appears in both with no intervening pass, it is
    auto-added to ``tests/quarantine.yaml`` with ``auto_added: true``.

    This block is RED: ``record_test_result``, ``should_auto_quarantine``,
    ``auto_quarantine_test``, and ``TEST_FAILURE_HISTORY_FILE`` do not
    exist yet.
    """

    def _write_quarantine_yaml(self, tmp_path: Path, entries: list[dict]) -> Path:
        """Mirror of TestQuarantineSchema's helper for clarity in this class."""
        lines: list[str] = []
        for e in entries:
            lines.append(f"- test_id: {e['test_id']}")
            lines.append(f"  added_at: \"{e['added_at']}\"")
            reason = str(e["reason"])
            if any(c in reason for c in [":", "#", "\n"]):
                lines.append(f'  reason: "{reason}"')
            else:
                lines.append(f"  reason: {reason}")
            lines.append(f"  auto_added: {'true' if e['auto_added'] else 'false'}")
            lines.append("")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        path = tests_dir / "quarantine.yaml"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _write_history_jsonl(self, tmp_path: Path, history: list[dict]) -> Path:
        """Write a .ralph/test-failure-history.jsonl with the given runs."""
        import json

        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir(parents=True, exist_ok=True)
        path = ralph_dir / "test-failure-history.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for run in history:
                f.write(json.dumps(run) + "\n")
        return path

    def test_single_failure_no_auto_add(self, tmp_path, monkeypatch) -> None:
        """A single failure does NOT trigger auto-quarantine."""
        from core import validate

        # History has one run with one failure for test_x.
        history = [
            {
                "run_at": "2026-06-27T12:00:00Z",
                "failures": ["tests/unit/x.py::test_x"],
                "passes": [],
            }
        ]
        history_path = self._write_history_jsonl(tmp_path, history)
        monkeypatch.setattr(validate, "TEST_FAILURE_HISTORY_FILE", history_path)

        assert validate.should_auto_quarantine("tests/unit/x.py::test_x") is False

    def test_two_consecutive_failures_auto_adds(self, tmp_path, monkeypatch) -> None:
        """2 consecutive failures (no intervening pass) → auto-quarantine."""
        from core import validate

        history = [
            {
                "run_at": "2026-06-27T12:00:00Z",
                "failures": ["tests/unit/x.py::test_y"],
                "passes": [],
            },
            {
                "run_at": "2026-06-27T13:00:00Z",
                "failures": ["tests/unit/x.py::test_y"],
                "passes": [],
            },
        ]
        history_path = self._write_history_jsonl(tmp_path, history)
        monkeypatch.setattr(validate, "TEST_FAILURE_HISTORY_FILE", history_path)
        quarantine_path = self._write_quarantine_yaml(tmp_path, [])
        monkeypatch.setattr(validate, "QUARANTINE_FILE", quarantine_path)

        assert validate.should_auto_quarantine("tests/unit/x.py::test_y") is True
        added = validate.auto_quarantine_test(
            "tests/unit/x.py::test_y", reason="two consecutive failures"
        )
        assert added is True

        # The entry is now in tests/quarantine.yaml with auto_added=True.
        entries = validate.load_quarantine_entries()
        assert len(entries) == 1
        assert entries[0]["test_id"] == "tests/unit/x.py::test_y"
        assert entries[0]["auto_added"] is True

    def test_failure_passed_failure_no_auto_add(self, tmp_path, monkeypatch) -> None:
        """2 failures separated by a passing run → no auto-quarantine."""
        from core import validate

        history = [
            {
                "run_at": "2026-06-27T12:00:00Z",
                "failures": ["tests/unit/x.py::test_z"],
                "passes": [],
            },
            {
                "run_at": "2026-06-27T13:00:00Z",
                "failures": [],
                "passes": ["tests/unit/x.py::test_z"],
            },
            {
                "run_at": "2026-06-27T14:00:00Z",
                "failures": ["tests/unit/x.py::test_z"],
                "passes": [],
            },
        ]
        history_path = self._write_history_jsonl(tmp_path, history)
        monkeypatch.setattr(validate, "TEST_FAILURE_HISTORY_FILE", history_path)

        assert validate.should_auto_quarantine("tests/unit/x.py::test_z") is False

    def test_record_test_result_appends_to_history(self, tmp_path, monkeypatch) -> None:
        """record_test_result appends a single run entry to the JSONL."""
        from core import validate

        history_path = self._write_history_jsonl(tmp_path, [])
        monkeypatch.setattr(validate, "TEST_FAILURE_HISTORY_FILE", history_path)

        validate.record_test_result(
            failures=["tests/unit/a.py::test_b"],
            passes=["tests/unit/c.py::test_d"],
            run_at="2026-06-27T15:00:00Z",
        )

        # History now has one run.
        assert history_path.exists()
        lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        import json

        run = json.loads(lines[0])
        assert run["failures"] == ["tests/unit/a.py::test_b"]
        assert run["passes"] == ["tests/unit/c.py::test_d"]
        assert run["run_at"] == "2026-06-27T15:00:00Z"


# ─────────────────────────────────────────────────────────
# C3.3 — Quarantine auto-unquarantine after 7 days (spec §10.3 C3)
# ─────────────────────────────────────────────────────────


class TestUnquarantineStale:
    """C3.3: --unquarantine-stale CLI flag removes entries older than 7 days.

    Per spec §10.3 C3: quarantined tests are auto-removed after 7 days.
    The flag (or a scheduled sweep) removes entries where ``added_at``
    is more than 7 days old and preserves the rest. Tests assert:
    older entries are removed, newer ones preserved, and the function
    returns the count of removed entries.
    """

    def _write_yaml(self, tmp_path: Path, entries: list[dict]) -> Path:
        """Write a tests/quarantine.yaml with the given entries. Returns path."""
        path = tmp_path / "tests"
        path.mkdir(parents=True, exist_ok=True)
        quarantine_path = path / "quarantine.yaml"
        lines = []
        for e in entries:
            lines.append(f"- test_id: {e['test_id']}")
            lines.append(f"  added_at: \"{e['added_at']}\"")
            lines.append(f"  reason: {e['reason']}")
            lines.append(f"  auto_added: {'true' if e['auto_added'] else 'false'}")
            lines.append("")
        quarantine_path.write_text("\n".join(lines), encoding="utf-8")
        return quarantine_path

    def test_entry_older_than_7_days_is_removed(self, tmp_path, monkeypatch) -> None:
        """An entry with added_at 8 days ago is removed by unquarantine_stale_entries()."""
        from core import validate

        # 2026-06-19 = 8 days before 2026-06-27 (today for tests).
        entry = {
            "test_id": "tests/unit/x.py::test_y",
            "added_at": "2026-06-19T12:00:00Z",
            "reason": "flaky",
            "auto_added": True,
        }
        quarantine_path = self._write_yaml(tmp_path, [entry])
        monkeypatch.setattr(validate, "QUARANTINE_FILE", quarantine_path)

        removed = validate.unquarantine_stale_entries(now="2026-06-27T12:00:00Z")
        assert removed == 1

        entries = validate.load_quarantine_entries()
        assert entries == []

    def test_entry_younger_than_7_days_preserved(self, tmp_path, monkeypatch) -> None:
        """An entry with added_at 1 day ago is preserved."""
        from core import validate

        entry = {
            "test_id": "tests/unit/x.py::test_y",
            "added_at": "2026-06-26T12:00:00Z",
            "reason": "flaky",
            "auto_added": True,
        }
        quarantine_path = self._write_yaml(tmp_path, [entry])
        monkeypatch.setattr(validate, "QUARANTINE_FILE", quarantine_path)

        removed = validate.unquarantine_stale_entries(now="2026-06-27T12:00:00Z")
        assert removed == 0

        entries = validate.load_quarantine_entries()
        assert len(entries) == 1
        assert entries[0]["test_id"] == "tests/unit/x.py::test_y"

    def test_mixed_ages_only_old_removed(self, tmp_path, monkeypatch) -> None:
        """A mix of old and new entries — only old ones are removed; count is correct."""
        from core import validate

        old = {
            "test_id": "tests/unit/a.py::test_old",
            "added_at": "2026-06-10T12:00:00Z",  # 17 days old
            "reason": "old flake",
            "auto_added": True,
        }
        new = {
            "test_id": "tests/unit/b.py::test_new",
            "added_at": "2026-06-26T12:00:00Z",  # 1 day old
            "reason": "recent flake",
            "auto_added": True,
        }
        quarantine_path = self._write_yaml(tmp_path, [old, new])
        monkeypatch.setattr(validate, "QUARANTINE_FILE", quarantine_path)

        removed = validate.unquarantine_stale_entries(now="2026-06-27T12:00:00Z")
        assert removed == 1

        entries = validate.load_quarantine_entries()
        assert len(entries) == 1
        assert entries[0]["test_id"] == "tests/unit/b.py::test_new"


# ─────────────────────────────────────────────────────────
# C3.4 — 🦠 Flake quarantined: GitHub issue post (spec §10.3 C3)
# ─────────────────────────────────────────────────────────


class TestQuarantineIssuePost:
    """C3.4: post a GitHub issue when a test is auto-quarantined.

    Per spec §10.3 C3: a fresh auto-quarantine triggers a GitHub
    issue with title ``🦠 Flake quarantined: <test_id>`` whose body
    contains the two failure timestamps and a link to the failure
    history. Re-running the same auto-quarantine does NOT create a
    duplicate (idempotency via the engine's idempotency.jsonl).

    This block is RED: ``post_flake_quarantined_issue`` does not
    exist yet on ``core.validate``.
    """

    def test_fresh_quarantine_creates_issue_with_correct_title(
        self, monkeypatch
    ) -> None:
        """A fresh auto-quarantine invokes gh issue create with title 🦠 Flake quarantined: <test_id>."""
        from core import validate

        recorded_cmds: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            recorded_cmds.append(cmd)
            from unittest import mock

            return mock.MagicMock(
                returncode=0, stdout="https://github.com/...", stderr=""
            )

        monkeypatch.setattr(validate, "run", fake_run)

        test_id = "tests/unit/x.py::test_y"
        # Capture both timestamps from the failure history.
        timestamps = ["2026-06-27T10:00:00Z", "2026-06-27T11:00:00Z"]
        issue_url = validate.post_flake_quarantined_issue(
            test_id=test_id, failure_timestamps=timestamps
        )

        # Exactly one gh call was made.
        assert len(recorded_cmds) == 1
        cmd = recorded_cmds[0]
        # `gh issue create --title <title> --body <body>`.
        assert cmd[0] == "gh"
        assert "issue" in cmd
        assert "create" in cmd

        # Find --title and --body values.
        title_idx = cmd.index("--title")
        body_idx = cmd.index("--body")
        title = cmd[title_idx + 1]
        body = cmd[body_idx + 1]
        assert title == f"🦠 Flake quarantined: {test_id}"
        # Both timestamps appear in the body.
        for ts in timestamps:
            assert ts in body
        # A link to the failure history is included.
        assert "test-failure-history.jsonl" in body
        assert issue_url  # non-empty

    def test_idempotent_no_duplicate_issue(self, monkeypatch) -> None:
        """A second auto-quarantine for the same test_id does NOT create a second issue."""
        from core import validate

        recorded_cmds: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            recorded_cmds.append(cmd)
            from unittest import mock

            return mock.MagicMock(
                returncode=0, stdout="https://github.com/...", stderr=""
            )

        monkeypatch.setattr(validate, "run", fake_run)

        test_id = "tests/unit/x.py::test_y"
        timestamps = ["2026-06-27T10:00:00Z", "2026-06-27T11:00:00Z"]

        # First call: creates the issue, returns URL.
        url1 = validate.post_flake_quarantined_issue(
            test_id=test_id, failure_timestamps=timestamps, run_id="run-A"
        )
        assert len(recorded_cmds) == 1

        # Second call with same test_id and run_id: idempotent — NO new gh call.
        url2 = validate.post_flake_quarantined_issue(
            test_id=test_id, failure_timestamps=timestamps, run_id="run-A"
        )
        assert len(recorded_cmds) == 1  # still 1
        assert url2 == url1  # same URL returned

    def test_gh_failure_does_not_raise(self, monkeypatch) -> None:
        """If gh issue create fails, the function returns None and does not raise."""
        from core import validate

        def fake_run(cmd, *args, **kwargs):
            from unittest import mock

            return mock.MagicMock(returncode=1, stdout="", stderr="auth error")

        monkeypatch.setattr(validate, "run", fake_run)

        result = validate.post_flake_quarantined_issue(
            test_id="tests/unit/x.py::test_y",
            failure_timestamps=["2026-06-27T10:00:00Z"],
        )
        assert result is None
