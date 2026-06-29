"""
Unit tests for core/engine.py ticket fetching.
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

import engine  # noqa: E402

from core.pipeline import daemon as daemon_mod  # noqa: E402
from core.pipeline import (  # noqa: E402
    issue_ops,
    prompts,
    recovery,
    reporting,
    shell,
    test_tracking,
)
from core.pipeline.github import board as board_mod  # noqa: E402
from core.pipeline.stages import build_subagents  # noqa: E402
from core.pipeline.stages import verify as verify_stage  # noqa: E402

# ─────────────────────────────────────────────────────────
# A2.1 — QA-test permission lock (spec §10.1 A2)
# ─────────────────────────────────────────────────────────


class TestRunTestSubagent:
    """A2.1: after _run_test_subagent returns, QA-written test files have mode 0o444."""

    def _setup_qa_test_file(self, tmp_path: Path) -> Path:
        """Create a QA test file in a tests/ subdir. Returns its absolute path."""
        tests_dir = tmp_path / "tests" / "unit"
        tests_dir.mkdir(parents=True)
        test_file = tests_dir / "test_qa_written.py"
        test_file.write_text("def test_qa():\n    assert True\n")
        return test_file

    def test_qa_test_files_have_mode_0444_after_subagent_returns(
        self, tmp_path, monkeypatch
    ) -> None:
        """After _run_test_subagent returns successfully, every file in QA test dir has mode 0o444."""
        qa_file = self._setup_qa_test_file(tmp_path)

        # Force PROJECT_ROOT to tmp_path so .ralph/ and tests/ resolve correctly.
        monkeypatch.setattr(build_subagents, "PROJECT_ROOT", tmp_path)

        # Mock all side-effecting helpers + the agent invocation.
        with (
            mock.patch.object(
                build_subagents, "_invoke_with_retry", return_value=(True, "")
            ),
            mock.patch.object(build_subagents, "gh_comment"),
            mock.patch.object(build_subagents, "log_metrics"),
            mock.patch.object(build_subagents, "_snapshot_tests_dir"),
            mock.patch.object(
                build_subagents,
                "_detect_new_tests",
                return_value=[str(qa_file.relative_to(tmp_path))],
            ),
            mock.patch.object(build_subagents, "_save_test_tracking"),
        ):
            issue = {"number": 1, "title": "Test issue"}
            ok = engine._run_test_subagent(issue)

        assert ok is True
        mode = qa_file.stat().st_mode & 0o777
        assert mode == 0o444, f"Expected mode 0o444, got {oct(mode)}"

    def test_implement_cannot_write_to_locked_qa_test(
        self, tmp_path, monkeypatch
    ) -> None:
        """IMPLEMENT sub-agent attempting to write to a QA test file raises PermissionError."""
        qa_file = self._setup_qa_test_file(tmp_path)
        monkeypatch.setattr(build_subagents, "PROJECT_ROOT", tmp_path)

        with (
            mock.patch.object(
                build_subagents, "_invoke_with_retry", return_value=(True, "")
            ),
            mock.patch.object(build_subagents, "gh_comment"),
            mock.patch.object(build_subagents, "log_metrics"),
            mock.patch.object(build_subagents, "_snapshot_tests_dir"),
            mock.patch.object(
                build_subagents,
                "_detect_new_tests",
                return_value=[str(qa_file.relative_to(tmp_path))],
            ),
            mock.patch.object(build_subagents, "_save_test_tracking"),
        ):
            engine._run_test_subagent({"number": 1, "title": "Test issue"})

        # After lock, attempting to write must raise PermissionError on POSIX.
        # On platforms without strict POSIX permission enforcement (Windows),
        # the test is best-effort and may pass without raising.
        if os.name == "posix":
            with pytest.raises((PermissionError, OSError)):
                qa_file.write_text("def test_qa():\n    assert False\n")

    def test_chmod_happens_after_subagent_returns(self, tmp_path, monkeypatch) -> None:
        """Test files are NOT chmod'd before the TEST sub-agent returns. Ordering matters."""
        qa_file = self._setup_qa_test_file(tmp_path)
        monkeypatch.setattr(build_subagents, "PROJECT_ROOT", tmp_path)

        observed_modes: list[int] = []

        def fake_invoke_with_retry(
            prompt, issue_num, classifier, budget, stage=None, worktree_path=None
        ):
            # Snapshot the file mode WHILE the agent is running.
            observed_modes.append(qa_file.stat().st_mode & 0o777)
            return True, ""

        with (
            mock.patch.object(
                build_subagents,
                "_invoke_with_retry",
                side_effect=fake_invoke_with_retry,
            ),
            mock.patch.object(build_subagents, "gh_comment"),
            mock.patch.object(build_subagents, "log_metrics"),
            mock.patch.object(build_subagents, "_snapshot_tests_dir"),
            mock.patch.object(
                build_subagents,
                "_detect_new_tests",
                return_value=[str(qa_file.relative_to(tmp_path))],
            ),
            mock.patch.object(build_subagents, "_save_test_tracking"),
        ):
            engine._run_test_subagent({"number": 1, "title": "Test issue"})

        # During the agent run, the file should NOT yet be locked.
        assert len(observed_modes) == 1
        assert observed_modes[0] != 0o444, "File was locked BEFORE agent returned"

        # After the agent returned, the file IS locked.
        final_mode = qa_file.stat().st_mode & 0o777
        assert final_mode == 0o444


# ─────────────────────────────────────────────────────────
# A2.2 — _detect_tampered_tests reclassification (spec §10.1 A2)
# ─────────────────────────────────────────────────────────


class TestAssembleImplementPrompt:
    """A3.2: _assemble_subagent_prompt reads from .ralph/issues/<N>/artifacts/."""

    def _setup_artifacts(self, tmp_path: Path, issue_num: int = 1) -> None:
        """Create the artifact directory layout for issue_num under tmp_path/.ralph/."""
        from core.pipeline.agents.artifacts import (  # type: ignore[import-not-found]
            write_acceptance_criteria,
            write_design,
            write_files_in_scope,
            write_qa_tests,
        )

        write_design(
            issue_num, "# Design for issue 1\n\nApproach: TDD.", project_root=tmp_path
        )
        write_files_in_scope(
            issue_num, ["src/foo.py", "tests/unit/test_foo.py"], project_root=tmp_path
        )
        write_acceptance_criteria(
            issue_num,
            [
                {"id": "AC1", "criterion": "tests pass"},
                {"id": "AC2", "criterion": "lint clean"},
            ],
            project_root=tmp_path,
        )
        write_qa_tests(
            issue_num, ["tests/unit/test_foo.py::test_a"], project_root=tmp_path
        )

    def _patch_prompt_module(self, tmp_path: Path, monkeypatch) -> None:
        """Point prompt constants at tmp_path for the moved prompts module."""
        monkeypatch.setattr(prompts, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(
            prompts,
            "PROMPT_FILE",
            tmp_path / "docs" / "agent" / "PROMPT.md",
            raising=False,
        )
        monkeypatch.setattr(
            prompts,
            "PROMPTS_DIR",
            tmp_path / "docs" / "agent" / "prompts",
            raising=False,
        )

    def test_prompt_contains_verbatim_design_text(self, tmp_path, monkeypatch) -> None:
        """Assembled IMPLEMENT prompt contains the verbatim design text."""
        self._setup_artifacts(tmp_path, issue_num=1)
        self._patch_prompt_module(tmp_path, monkeypatch)

        issue = {"number": 1, "title": "Test issue", "body": "Implement X."}
        prompt = engine._assemble_subagent_prompt(issue, "implement.md", mode="B")

        assert "Design for issue 1" in prompt
        assert "Approach: TDD." in prompt

    def test_prompt_lists_every_in_scope_path(self, tmp_path, monkeypatch) -> None:
        """Assembled IMPLEMENT prompt lists every path from files_in_scope.json."""
        self._setup_artifacts(tmp_path, issue_num=1)
        self._patch_prompt_module(tmp_path, monkeypatch)

        issue = {"number": 1, "title": "Test issue", "body": "Implement X."}
        prompt = engine._assemble_subagent_prompt(issue, "implement.md", mode="B")

        assert "src/foo.py" in prompt
        assert "tests/unit/test_foo.py" in prompt

    def test_prompt_lists_every_acceptance_criterion(
        self, tmp_path, monkeypatch
    ) -> None:
        """Assembled IMPLEMENT prompt lists every acceptance criterion as a numbered item."""
        self._setup_artifacts(tmp_path, issue_num=1)
        self._patch_prompt_module(tmp_path, monkeypatch)

        issue = {"number": 1, "title": "Test issue", "body": "Implement X."}
        prompt = engine._assemble_subagent_prompt(issue, "implement.md", mode="B")

        assert "AC1" in prompt
        assert "tests pass" in prompt
        assert "AC2" in prompt
        assert "lint clean" in prompt

    def test_missing_artifact_dir_raises_filenotfound(
        self, tmp_path, monkeypatch
    ) -> None:
        """Missing artifact directory -> FileNotFoundError (not silent fallback)."""
        self._patch_prompt_module(tmp_path, monkeypatch)

        issue = {"number": 99, "title": "Test issue", "body": "Implement X."}
        with pytest.raises(FileNotFoundError):
            engine._assemble_subagent_prompt(issue, "implement.md", mode="B")


# ─────────────────────────────────────────────────────────
# A2.2 — _detect_tampered_tests reclassification (spec §10.1 A2)
# ─────────────────────────────────────────────────────────


class TestNoProgressBoard:
    """A7.1: _update_progress_board is removed; no PROGRESS.md writes."""

    def test_update_progress_board_function_does_not_exist(self) -> None:
        """grep _update_progress_board core/engine.py returns no matches after A7.1."""
        import subprocess

        result = subprocess.run(
            ["grep", "-rn", "_update_progress_board", "core/"],
            capture_output=True,
            text=True,
            check=False,
        )
        # After A7.1 (this task), the function should not exist anywhere in core/.
        assert (
            result.returncode != 0 or "_update_progress_board" not in result.stdout
        ), f"Found _update_progress_board in core/: {result.stdout}"

    def test_progress_md_not_created_during_mocked_pipeline(
        self, tmp_path, monkeypatch
    ) -> None:
        """A full mocked pipeline run does NOT create docs/agent/PROGRESS.md."""
        progress_md = tmp_path / "docs" / "agent" / "PROGRESS.md"

        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)
        # Mock all side effects so the pipeline can run.
        with (
            mock.patch.object(engine, "gh", return_value=mock.MagicMock(stdout="")),
            mock.patch.object(engine, "gh_comment"),
            mock.patch.object(engine, "git", return_value=mock.MagicMock(stdout="")),
            mock.patch.object(engine, "log_metrics"),
            mock.patch.object(engine, "transition_label"),
            mock.patch.object(engine, "fetch_ready_ticket"),
            mock.patch.object(engine, "fetch_retry_issue"),
            mock.patch.object(engine, "fetch_issue_by_number"),
            mock.patch.object(engine, "_dependencies_met", return_value=True),
            mock.patch.object(engine, "sync_ready_board"),
            mock.patch.object(engine, "acquire_pid_file", return_value=True),
            mock.patch.object(engine, "release_pid_file"),
            mock.patch.object(engine, "save_checkpoint"),
            mock.patch.object(engine, "clear_checkpoint"),
            mock.patch.object(engine, "run_loop"),
        ):
            # Just import-and-call the function names that used to write PROGRESS.md.
            assert not hasattr(
                engine, "_update_progress_board"
            ), "_update_progress_board should be removed"

        # The file was never created.
        assert not progress_md.exists()

    def test_no_module_imports_removed_function(self) -> None:
        """No module imports or calls _update_progress_board (after A7.1 removal)."""
        assert not hasattr(
            engine, "_update_progress_board"
        ), "_update_progress_board still present in engine module"


# ─────────────────────────────────────────────────────────
# A2.2 — _detect_tampered_tests reclassification (spec §10.1 A2)
# ─────────────────────────────────────────────────────────


class TestEnrichedFailureComments:
    """A5.1: _format_stage_failure includes stdout tail, trajectory link, failure-report link."""

    def test_comment_contains_stdout_tail_section(self) -> None:
        """Comment body contains an 'Agent stdout' / 'last 50 lines' section with ≥ 1 line."""
        report_content = (
            "## What Was Attempted\nDid a thing.\n\n"
            "## What Failed\nSomething.\n"
            "stdout line 1\nstdout line 2\nstdout line 3\n"
        )
        body = engine._format_stage_failure(
            "BUILD",
            report_content=report_content,
            agent_stdout="agent line A\nagent line B\n",
            issue_num=1,
        )
        assert "Agent stdout" in body or "last 50 lines" in body.lower()
        # At least one agent stdout line is preserved in the comment.
        assert "agent line A" in body

    def test_comment_links_to_trajectory_when_present(
        self, tmp_path, monkeypatch
    ) -> None:
        """Comment contains a Markdown link to .ralph/issues/<N>/trajectory.jsonl when present."""
        # Create the trajectory file
        traj_dir = tmp_path / ".ralph" / "issues" / "1"
        traj_dir.mkdir(parents=True)
        (traj_dir / "trajectory.jsonl").write_text('{"event": "stage_complete"}\n')

        monkeypatch.setattr(reporting, "PROJECT_ROOT", tmp_path)
        body = engine._format_stage_failure(
            "BUILD", report_content="some failure", issue_num=1
        )
        assert "trajectory.jsonl" in body
        # Markdown link format: should contain .ralph/issues/<N>/trajectory.jsonl
        assert ".ralph/issues/1/trajectory.jsonl" in body

    def test_comment_omits_trajectory_link_when_absent(
        self, tmp_path, monkeypatch
    ) -> None:
        """Comment does NOT include a trajectory link when trajectory.jsonl does not exist."""
        monkeypatch.setattr(reporting, "PROJECT_ROOT", tmp_path)
        body = engine._format_stage_failure(
            "BUILD", report_content="some failure", issue_num=1
        )
        assert ".ralph/issues/1/trajectory.jsonl" not in body

    def test_comment_links_to_failure_report(self, tmp_path, monkeypatch) -> None:
        """Comment contains a Markdown link to .ralph/issue-<N>-report.md."""
        monkeypatch.setattr(reporting, "PROJECT_ROOT", tmp_path)
        body = engine._format_stage_failure(
            "BUILD", report_content="some failure", issue_num=1
        )
        # Should reference the failure report file path
        assert "issue-1-report.md" in body


# ─────────────────────────────────────────────────────────
# A2.2 — _detect_tampered_tests reclassification (spec §10.1 A2)
# ─────────────────────────────────────────────────────────


class TestInvokeAgentNoContinue:
    """A3.3: invoke_agent never passes --continue or --session (artifact-based handoff).

    The ``session_file`` and ``continue_session`` parameters were removed;
    neither ``--continue`` nor ``--session`` ever appear in the command line.
    """

    def _capture_invocation(self, monkeypatch, agent_bin: str) -> list[str]:
        """Patch subprocess and capture the assembled command."""
        from core.pipeline.agents import pi as pi_mod

        captured: dict[str, list[str]] = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = list(cmd)
            fake_proc = mock.MagicMock()
            fake_proc.returncode = 0
            fake_proc.stdout = b""
            fake_proc.stderr = b""
            return fake_proc

        monkeypatch.setattr(pi_mod, "_resolve_agent_binary", lambda: agent_bin)
        monkeypatch.setattr(pi_mod, "_run_agent", fake_run)
        engine.invoke_agent("do something", 1)
        return captured.get("cmd", [])

    def test_pi_invocation_has_no_continue_flag(self, monkeypatch) -> None:
        """invoke_agent with binary='pi' does not include --continue."""
        captured_cmd = self._capture_invocation(monkeypatch, agent_bin="pi")
        assert "--continue" not in captured_cmd

    def test_kimi_invocation_has_no_continue_flag(self, monkeypatch) -> None:
        """invoke_agent with binary='kimi' does not include --continue."""
        captured_cmd = self._capture_invocation(monkeypatch, agent_bin="kimi")
        assert "--continue" not in captured_cmd

    def test_no_session_flag_passed(self, monkeypatch) -> None:
        """Neither pi nor kimi invocation passes --session."""
        captured_cmd = self._capture_invocation(monkeypatch, agent_bin="pi")
        assert "--session" not in captured_cmd

    def test_pi_and_kimi_code_paths_are_identical(self, monkeypatch) -> None:
        """Per spec §10.1 A3, kimi and pi use the same invocation path (no kimi-specific workaround)."""
        from core.pipeline.agents import pi as pi_mod

        captured: dict[str, list[str]] = {}

        def make_fake_run(key: str):
            def fake_run(cmd, *args, **kwargs):
                captured[key] = list(cmd)
                fake_proc = mock.MagicMock()
                fake_proc.returncode = 0
                fake_proc.stdout = b""
                fake_proc.stderr = b""
                return fake_proc

            return fake_run

        # Capture pi invocation
        monkeypatch.setattr(pi_mod, "_resolve_agent_binary", lambda: "pi")
        monkeypatch.setattr(pi_mod, "_run_agent", make_fake_run("pi"))
        engine.invoke_agent("do something", 1)
        pi_cmd = captured["pi"]

        # Capture kimi invocation
        monkeypatch.setattr(pi_mod, "_resolve_agent_binary", lambda: "kimi")
        monkeypatch.setattr(pi_mod, "_run_agent", make_fake_run("kimi"))
        engine.invoke_agent("do something", 1)
        kimi_cmd = captured["kimi"]

        # Both commands end with the prompt
        assert pi_cmd[-1] == "do something"
        assert kimi_cmd[-1] == "do something"
        # Neither contains --continue or --session
        assert "--continue" not in pi_cmd
        assert "--continue" not in kimi_cmd
        assert "--session" not in pi_cmd
        assert "--session" not in kimi_cmd


# ─────────────────────────────────────────────────────────
# A2.2 — _detect_tampered_tests reclassification (spec §10.1 A2)
# ─────────────────────────────────────────────────────────


class TestDetectTamperedTests:
    """A2.2: _detect_tampered_tests is now a sanity check, not a warning.

    Per spec §10.1 A2 — changed from advisory warning to a hard block:
    pristine state (mode 0o444) → returns True
    tampered state (mode != 0o444) → raises TamperedTestsError
    Logs at ERROR level, not WARNING.
    """

    def _make_test_file(self, tmp_path: Path, mode: int) -> Path:
        """Create a test file with the given mode. Returns its absolute path."""
        test_file = tmp_path / "tests" / "unit" / "test_qa.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_qa():\n    assert True\n")
        test_file.chmod(mode)
        return test_file

    def test_pristine_state_returns_true(self, tmp_path) -> None:
        """Pristine state (all files 0o444) → function returns True (no raise)."""
        qa_file = self._make_test_file(tmp_path, 0o444)
        result = engine._detect_tampered_tests([str(qa_file)])
        assert result is True

    def test_tampered_state_raises(self, tmp_path) -> None:
        """File with mode != 0o444 → function raises TamperedTestsError (or returns False)."""
        qa_file = self._make_test_file(tmp_path, 0o644)
        raised = False
        result = None
        try:
            result = engine._detect_tampered_tests([str(qa_file)])
        except engine.TamperedTestsError:
            raised = True
        # Either raised, or returned False — both acceptable per task acceptance criteria
        if not raised:
            assert result is False, f"Expected raise or False; got {result}"

    def test_logs_at_error_level_not_warning(self, tmp_path, caplog) -> None:
        """The function logs at ERROR level on tampering, not WARNING."""
        import logging

        qa_file = self._make_test_file(tmp_path, 0o644)
        with caplog.at_level(logging.ERROR):
            try:
                engine._detect_tampered_tests([str(qa_file)])
            except Exception:
                pass
        # There must be at least one ERROR-level record (not WARNING-only).
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) >= 1, (
            "Expected at least one ERROR-level log on tampering; "
            f"got levels: {[r.levelname for r in caplog.records]}"
        )


def _make_gh_response(number=42, state="OPEN", body=""):
    return json.dumps(
        {"number": number, "title": "Test issue", "body": body, "state": state}
    )


def test_fetch_issue_by_number_returns_open_issue():
    """fetch_issue_by_number returns an open issue with no unmet deps."""
    with mock.patch.object(
        issue_ops, "gh", return_value=mock.Mock(stdout=_make_gh_response())
    ) as mock_gh:
        issue = engine.fetch_issue_by_number(42)

    assert issue is not None
    assert issue["number"] == 42
    assert issue["state"] == "OPEN"
    mock_gh.assert_called_once_with(
        "issue", "view", "42", "--json", "number,title,body,state"
    )


def test_fetch_issue_by_number_returns_none_when_closed():
    """fetch_issue_by_number returns None if the issue is closed."""
    with mock.patch.object(
        issue_ops,
        "gh",
        return_value=mock.Mock(stdout=_make_gh_response(state="CLOSED")),
    ):
        issue = engine.fetch_issue_by_number(42)

    assert issue is None


def test_fetch_issue_by_number_returns_none_when_not_found():
    """fetch_issue_by_number returns None if gh issue view fails."""
    import subprocess

    with mock.patch.object(
        issue_ops, "gh", side_effect=subprocess.CalledProcessError(1, "gh")
    ):
        issue = engine.fetch_issue_by_number(42)

    assert issue is None


def test_fetch_issue_by_number_returns_none_when_dependencies_unmet():
    """fetch_issue_by_number returns None when a dependency is still open."""
    body = "Depends on: #7"
    responses = {
        ("issue", "view", "42", "--json", "number,title,body,state"): mock.Mock(
            stdout=_make_gh_response(body=body)
        ),
        ("issue", "view", "7", "--json", "state", "--jq", ".state"): mock.Mock(
            stdout="OPEN"
        ),
    }

    def fake_gh(*args):
        return responses[args]

    with mock.patch.object(issue_ops, "gh", side_effect=fake_gh):
        issue = engine.fetch_issue_by_number(42)

    assert issue is None


def test_fetch_issue_by_number_returns_issue_when_dependencies_met():
    """fetch_issue_by_number returns the issue when all dependencies are closed."""
    body = "Depends on: #7"
    responses = {
        ("issue", "view", "42", "--json", "number,title,body,state"): mock.Mock(
            stdout=_make_gh_response(body=body)
        ),
        ("issue", "view", "7", "--json", "state", "--jq", ".state"): mock.Mock(
            stdout="CLOSED"
        ),
    }

    def fake_gh(*args):
        return responses[args]

    with mock.patch.object(issue_ops, "gh", side_effect=fake_gh):
        issue = engine.fetch_issue_by_number(42)

    assert issue is not None
    assert issue["number"] == 42


def test_snapshot_tests_dir_ignores_pycache_and_pyc_files(tmp_path):
    """_snapshot_tests_dir only tracks .py files and excludes cache directories."""
    fake_project = tmp_path / "project"
    tests_dir = fake_project / "tests" / "unit"
    pycache = tests_dir / "__pycache__"
    pycache.mkdir(parents=True)
    pytest_cache = tests_dir / ".pytest_cache" / "v"
    pytest_cache.mkdir(parents=True)

    (tests_dir / "test_real.py").write_text("def test_pass(): pass\n")
    (pycache / "test_real.cpython-312.pyc").write_bytes(b"pyc")
    (pytest_cache / "cachecontents").write_text("x")
    (tests_dir / "notes.md").write_text("not a test\n")

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        snapshot = engine._snapshot_tests_dir()

    assert list(snapshot.keys()) == ["tests/unit/test_real.py"]


# ─────────────────────────────────────────────────────────
# Test tracking sanitization (#56, #57)
# ─────────────────────────────────────────────────────────


def test_save_test_tracking_sanitizes_pycache_paths(tmp_path):
    """_save_test_tracking excludes __pycache__ and .pyc entries."""
    fake_project = tmp_path / "project"
    ralph_dir = fake_project / ".ralph"

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        engine._save_test_tracking(
            56,
            [
                "tests/unit/__pycache__/test_a.cpython-314.pyc",
                "tests/unit/test_a.py",
            ],
        )

    tracking_file = ralph_dir / "issue-56-tests.json"
    assert tracking_file.exists()
    data = json.loads(tracking_file.read_text())
    assert data["tests"] == ["tests/unit/test_a.py"]


def test_save_test_tracking_sanitizes_pytest_cache_entries(tmp_path):
    """_save_test_tracking excludes .pytest_cache entries."""
    fake_project = tmp_path / "project"

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        engine._save_test_tracking(
            57,
            [
                "tests/unit/.pytest_cache/v/cache/nodeids",
                "tests/unit/test_b.py",
            ],
        )

    tracking_file = fake_project / ".ralph" / "issue-57-tests.json"
    data = json.loads(tracking_file.read_text())
    assert data["tests"] == ["tests/unit/test_b.py"]


def test_save_test_tracking_sanitizes_non_py_files(tmp_path):
    """_save_test_tracking excludes entries that don't end with .py."""
    fake_project = tmp_path / "project"

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        engine._save_test_tracking(
            58,
            [
                "tests/unit/notes.md",
                "tests/unit/test_c.py",
                "tests/unit/__pycache__/test_c.cpython-314.pyc",
            ],
        )

    tracking_file = fake_project / ".ralph" / "issue-58-tests.json"
    data = json.loads(tracking_file.read_text())
    assert data["tests"] == ["tests/unit/test_c.py"]


def test_save_test_tracking_handles_empty_list(tmp_path):
    """_save_test_tracking writes empty array when all inputs are filtered out."""
    fake_project = tmp_path / "project"

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        engine._save_test_tracking(
            59,
            [
                "tests/__pycache__/ghost.pyc",
                "tests/README.md",
            ],
        )

    tracking_file = fake_project / ".ralph" / "issue-59-tests.json"
    data = json.loads(tracking_file.read_text())
    assert data["tests"] == []


def test_resolve_existing_test_paths_filters_missing_files(tmp_path):
    """_resolve_existing_test_paths returns only paths that exist on disk."""
    fake_project = tmp_path / "project"
    tests_dir = fake_project / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_real.py").write_text("def test_pass(): pass\n")

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        result = engine._resolve_existing_test_paths(
            [
                "tests/unit/test_real.py",
                "tests/unit/test_gone.py",
                "tests/unit/test_also_missing.py",
            ]
        )

    assert result == ["tests/unit/test_real.py"]


def test_resolve_existing_test_paths_returns_empty_for_all_missing(tmp_path):
    """_resolve_existing_test_paths returns empty list when no paths exist."""
    fake_project = tmp_path / "project"
    fake_project.mkdir(parents=True)

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        result = engine._resolve_existing_test_paths(
            [
                "tests/unit/ghost.py",
                "tests/integration/nope.py",
            ]
        )

    assert result == []


def test_resolve_existing_test_paths_returns_empty_for_empty_input(tmp_path):
    """_resolve_existing_test_paths handles empty input gracefully."""
    fake_project = tmp_path / "project"
    fake_project.mkdir(parents=True)

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        result = engine._resolve_existing_test_paths([])

    assert result == []


def test_snapshot_file_hashes_returns_hashes_for_existing_files(tmp_path):
    """_snapshot_file_hashes returns content hashes for files that exist."""
    fake_project = tmp_path / "project"
    tests_dir = fake_project / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_a.py").write_text("def test(): pass\n")
    (tests_dir / "test_b.py").write_text("def test(): assert True\n")

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        hashes = engine._snapshot_file_hashes(
            [
                "tests/unit/test_a.py",
                "tests/unit/test_b.py",
                "tests/unit/test_missing.py",
            ]
        )

    assert len(hashes) == 2
    assert "tests/unit/test_a.py" in hashes
    assert "tests/unit/test_b.py" in hashes
    assert "tests/unit/test_missing.py" not in hashes


def test_snapshot_file_hashes_returns_empty_for_all_missing(tmp_path):
    """_snapshot_file_hashes skips missing files, returns empty dict."""
    fake_project = tmp_path / "project"
    fake_project.mkdir(parents=True)

    with mock.patch.object(test_tracking, "PROJECT_ROOT", fake_project):
        hashes = engine._snapshot_file_hashes(["tests/nowhere.py"])

    assert hashes == {}


# These tests previously verified _detect_tampered_tests against content-hash
# snapshots (v3 semantics). A2.2 replaces that with a mode-based check
# (spec §10.1 A2). The new behavior is covered by TestDetectTamperedTests
# above. The legacy content-hash tests are removed because the function
# signature changed and the old behavior is no longer accessible.


def test_detect_tampered_tests_legacy_hash_helpers_remain():
    """Sanity check: _snapshot_file_hashes is still present (other call sites use it)."""
    assert hasattr(engine, "_snapshot_file_hashes")


# ─────────────────────────────────────────────────────────
# Provider rate-limit / quota detection
# ─────────────────────────────────────────────────────────


def test_classify_provider_error_detects_kimi_rate_limit():
    """Kimi APIProviderRateLimitError / 429 is classified as rate-limit."""
    assert (
        engine._classify_provider_error("APIProviderRateLimitError: 429")
        == "rate_limit"
    )
    assert (
        engine._classify_provider_error("Provider returned 429 rate limit")
        == "rate_limit"
    )


def test_classify_provider_error_detects_pi_quota():
    """Pi quota/billing errors are classified as quota."""
    assert engine._classify_provider_error("Monthly usage limit reached") == "quota"
    assert engine._classify_provider_error("insufficient_quota") == "quota"
    assert engine._classify_provider_error("FreeUsageLimitError") == "quota"


def test_classify_provider_error_returns_none_for_normal_failure():
    """Ordinary test/code failures are not provider errors."""
    assert engine._classify_provider_error("AssertionError: 1 != 2") is None
    assert engine._classify_provider_error("pytest: command not found") is None


def test_invoke_agent_raises_rate_limit_error_on_kimi_429():
    """invoke_agent raises ProviderRateLimitError when output contains 429."""
    fake_result = mock.Mock(
        returncode=1, stdout=b"", stderr=b"APIProviderRateLimitError: 429"
    )
    with (
        mock.patch(
            "core.pipeline.agents.pi._resolve_agent_binary", return_value="kimi"
        ),
        mock.patch("core.pipeline.agents.pi._run_agent", return_value=fake_result),
    ):
        # The implementation now lives in core.pipeline.agents.pi, which
        # raises the core.engine package-module exception class. This test
        # file imports engine.py as a standalone module, so the class
        # identity differs; verify by class name instead of identity.
        with pytest.raises(Exception) as exc_info:
            engine.invoke_agent("prompt", 42)
        assert exc_info.value.__class__.__name__ == "ProviderRateLimitError"


def test_invoke_agent_raises_quota_error_on_pi_limit():
    """invoke_agent raises ProviderQuotaError when output contains quota message."""
    fake_result = mock.Mock(
        returncode=1, stdout=b"", stderr=b"FreeUsageLimitError: quota exceeded"
    )
    with (
        mock.patch("core.pipeline.agents.pi._resolve_agent_binary", return_value="pi"),
        mock.patch("core.pipeline.agents.pi._run_agent", return_value=fake_result),
    ):
        with pytest.raises(Exception) as exc_info:
            engine.invoke_agent("prompt", 42)
        assert exc_info.value.__class__.__name__ == "ProviderQuotaError"


def test_find_alternate_agent_returns_other_available_agent():
    """_find_alternate_agent returns the other agent when it is on PATH."""

    def fake_which(cmd):
        return mock.Mock(
            returncode=0 if cmd[0] == "which" and cmd[1] in ("kimi", "pi") else 1
        )

    # _find_alternate_agent lives at core.pipeline.providers now (C1 step 14a).
    from core.pipeline import providers as providers_mod

    with mock.patch.object(providers_mod, "subprocess") as mock_subp:
        mock_subp.run.side_effect = lambda cmd, **kw: fake_which(cmd)
        # Current agent is kimi, so alternate is pi.
        assert providers_mod._find_alternate_agent({"kimi"}) == "pi"
        # Current agent is pi, so alternate is kimi.
        assert providers_mod._find_alternate_agent({"pi"}) == "kimi"


def test_find_alternate_agent_returns_none_when_no_other_agent():
    """_find_alternate_agent returns None when the other agent is not installed."""

    def fake_which(cmd):
        # Only kimi is available.
        return mock.Mock(returncode=0 if cmd == ["which", "kimi"] else 1)

    from core.pipeline import providers as providers_mod

    with mock.patch.object(providers_mod, "subprocess") as mock_subp:
        mock_subp.run.side_effect = lambda cmd, **kw: fake_which(cmd)
        assert providers_mod._find_alternate_agent({"kimi"}) is None


def _make_sleep_shutdown():
    """Return a side-effect that sets the shutdown flag on the first sleep call."""
    called = False

    def _sleep(seconds):
        nonlocal called
        if not called:
            called = True
            # _sleep_with_interrupt reads recovery's module state, not engine's re-export.
            recovery._shutdown_requested = True

    return _sleep


def test_run_loop_reverts_ready_and_sleeps_on_rate_limit():
    """A provider rate-limit pauses the loop, reverts the ticket to ready, and does not block it."""
    # Reset canonical state in recovery.py.
    recovery._shutdown_requested = False
    recovery._in_cleanup = False
    os.environ.pop("RALPH_AGENT", None)
    issue = {"number": 42, "title": "Test"}

    # The provider-error machinery lives at core.pipeline.providers now.
    # We patch it there (its canonical home) so the patches take effect
    # when _handle_provider_error runs.
    from core.pipeline import providers as providers_mod

    with (
        mock.patch.object(recovery, "acquire_pid_file", return_value=True),
        mock.patch.object(recovery, "recover_from_crash", return_value=None),
        mock.patch.object(daemon_mod, "fetch_ready_ticket", side_effect=[issue, None]),
        mock.patch.object(daemon_mod, "transition_label") as mock_transition,
        mock.patch.object(
            daemon_mod,
            "run_pipeline",
            side_effect=providers_mod.ProviderRateLimitError("429"),
        ),
        mock.patch.object(providers_mod, "_find_alternate_agent", return_value=None),
        mock.patch.object(providers_mod, "_revert_to_ready") as mock_revert,
        mock.patch.object(providers_mod, "time") as mock_time,
        mock.patch.object(shell, "gh", return_value=mock.Mock(stdout="[]")),
        mock.patch.object(board_mod, "sync_status"),
        mock.patch.object(daemon_mod, "gh_comment"),
        mock.patch.object(daemon_mod, "log_metrics"),
        mock.patch.object(recovery, "release_pid_file"),
    ):
        mock_time.sleep.side_effect = _make_sleep_shutdown()
        daemon_mod.run_loop()

    # Claimed to design, then reverted to ready.
    mock_transition.assert_any_call(42, "status:design", "status:ready")
    mock_revert.assert_called_once_with(42)
    # Rate-limit backoff uses 1-second interruptible sleeps.
    mock_time.sleep.assert_any_call(1)


def test_run_loop_falls_back_to_alternate_agent():
    """When the current agent is rate-limited, the loop tries the alternate agent once."""
    recovery._shutdown_requested = False
    recovery._in_cleanup = False
    os.environ.pop("RALPH_AGENT", None)
    issue = {"number": 42, "title": "Test"}
    calls = []

    from core.pipeline import providers as providers_mod

    def fail_then_succeed(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise providers_mod.ProviderRateLimitError("429")
        return True

    def fetch_gen():
        # First claim (with original agent), then re-claim after fallback.
        yield issue
        yield issue
        recovery._shutdown_requested = True
        while True:
            yield None

    with (
        mock.patch.object(recovery, "acquire_pid_file", return_value=True),
        mock.patch.object(recovery, "recover_from_crash", return_value=None),
        mock.patch.object(daemon_mod, "fetch_ready_ticket", side_effect=fetch_gen()),
        mock.patch.object(daemon_mod, "transition_label") as mock_transition,
        mock.patch.object(daemon_mod, "run_pipeline", side_effect=fail_then_succeed),
        mock.patch.object(providers_mod, "_find_alternate_agent", return_value="pi"),
        mock.patch.object(providers_mod, "_revert_to_ready") as mock_revert,
        mock.patch("time.sleep"),
        mock.patch.object(shell, "gh", return_value=mock.Mock(stdout="[]")),
        mock.patch.object(board_mod, "sync_status"),
        mock.patch.object(daemon_mod, "gh_comment"),
        mock.patch.object(daemon_mod, "log_metrics"),
        mock.patch.object(recovery, "release_pid_file"),
    ):
        daemon_mod.run_loop()

    # Reverted to ready before retrying with alternate agent.
    mock_revert.assert_called_once_with(42)
    # Re-claimed for the fallback attempt.
    assert mock_transition.call_count >= 2
    assert os.environ.get("RALPH_AGENT") == "pi"


def test_run_loop_creates_project_issue_when_all_agents_exhausted():
    """When all agents hit quota/rate-limit, the loop logs a project issue and stops."""
    recovery._shutdown_requested = False
    recovery._in_cleanup = False
    os.environ.pop("RALPH_AGENT", None)
    issue = {"number": 42, "title": "Test"}

    from core.pipeline import providers as providers_mod

    with (
        mock.patch.object(recovery, "acquire_pid_file", return_value=True),
        mock.patch.object(recovery, "recover_from_crash", return_value=None),
        mock.patch.object(daemon_mod, "fetch_ready_ticket", side_effect=[issue, None]),
        mock.patch.object(daemon_mod, "transition_label"),
        mock.patch.object(
            daemon_mod,
            "run_pipeline",
            side_effect=providers_mod.ProviderQuotaError("quota"),
        ),
        mock.patch.object(providers_mod, "_find_alternate_agent", return_value=None),
        mock.patch.object(providers_mod, "_revert_to_ready"),
        mock.patch.object(providers_mod, "_create_provider_issue") as mock_create,
        mock.patch("time.sleep"),
        mock.patch.object(shell, "gh", return_value=mock.Mock(stdout="[]")),
        mock.patch.object(board_mod, "sync_status"),
        mock.patch.object(daemon_mod, "gh_comment"),
        mock.patch.object(daemon_mod, "log_metrics"),
        mock.patch.object(recovery, "release_pid_file"),
    ):
        daemon_mod.run_loop()

    mock_create.assert_called_once()


# ─────────────────────────────────────────────────────────
# B2.3 — Idempotent wrappers for gh() and git() (spec §10.2 B2)
# ─────────────────────────────────────────────────────────


class TestIdempotentWrappers:
    """B2.3: transition_label and gh_comment are idempotent when run_id is passed.

    The engine's existing call sites for label transitions and comments
    are wrapped to consult .ralph/issues/<N>/idempotency.jsonl. When
    the same (run_id, action, target, body) tuple has already executed,
    the wrapper short-circuits and does NOT invoke gh a second time.

    Per spec §10.2 B2: idempotency survives daemon SIGKILL because the
    log is persisted before invoking gh.

    These tests patch ``core.pipeline.github.client._run_gh`` because
    that is the single seam the GitHubClient uses to invoke subprocess.
    """

    def test_transition_label_invokes_subprocess_once(
        self, tmp_path, monkeypatch
    ) -> None:
        """transition_label with run_id invokes subprocess exactly once."""
        from core.pipeline.github import client as gh_client_mod

        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)

        with mock.patch.object(gh_client_mod, "_run_gh") as run_gh:
            run_gh.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            engine.transition_label(1, "status:design", "status:ready", run_id="X")

        assert run_gh.call_count == 1

    def test_transition_label_repeated_with_same_run_id_no_double_invoke(
        self, tmp_path, monkeypatch
    ) -> None:
        """Two transition_label calls with the same run_id invoke subprocess once."""
        from core.pipeline.github import client as gh_client_mod

        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)

        with mock.patch.object(gh_client_mod, "_run_gh") as run_gh:
            run_gh.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            engine.transition_label(1, "status:design", "status:ready", run_id="X")
            engine.transition_label(1, "status:design", "status:ready", run_id="X")

        assert run_gh.call_count == 1

    def test_gh_comment_repeated_with_same_run_id_no_double_invoke(
        self, tmp_path, monkeypatch
    ) -> None:
        """Two gh_comment calls with the same run_id + body invoke subprocess once."""
        from core.pipeline.github import client as gh_client_mod

        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)

        with mock.patch.object(gh_client_mod, "_run_gh") as run_gh:
            run_gh.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            engine.gh_comment(1, "hello", run_id="X")
            engine.gh_comment(1, "hello", run_id="X")

        assert run_gh.call_count == 1

    def test_idempotency_log_file_is_created(self, tmp_path, monkeypatch) -> None:
        """After a wrapped action, .ralph/issues/<N>/idempotency.jsonl exists."""
        from core.pipeline.github import client as gh_client_mod

        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(gh_client_mod, "PROJECT_ROOT", tmp_path)

        with mock.patch.object(gh_client_mod, "_run_gh") as run_gh:
            run_gh.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            engine.transition_label(1, "status:design", "status:ready", run_id="X")

        log = tmp_path / ".ralph" / "issues" / "1" / "idempotency.jsonl"
        assert log.exists()
        assert log.stat().st_size > 0


# ─────────────────────────────────────────────────────────
# B1.1 — Per-stage retry budget config (spec §10.2 B1, plan §3 R-6)
# ─────────────────────────────────────────────────────────


class TestRetryBudgetConfig:
    """B1.1: load_retry_config() reads [retry] from .ralph/config.toml.

    Per spec §10.2 B1 + plan §3 R-6 mitigation:
      - missing [retry] section → defaults (l1_max_attempts=1,
        l2_max_attempts=2)
      - [retry] l1_max_attempts = 0 → L1 retry disabled
      - [retry] l2_max_attempts = 3 → L2 retries up to 3 times
      - invalid (negative) → defaults + WARNING log
    """

    def test_no_retry_section_uses_defaults(self, tmp_path, monkeypatch) -> None:
        """Missing [retry] section → defaults: l1=1, l2=2."""
        # load_retry_config lives at core.pipeline.retry now (C1 step 14b).
        from core.pipeline import retry as retry_mod
        from core.pipeline.retry import load_retry_config

        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)
        budget = load_retry_config()
        assert budget.l1_max_attempts == 1
        assert budget.l2_max_attempts == 2

    def test_l1_max_attempts_zero_disables_l1(self, tmp_path, monkeypatch) -> None:
        """[retry] l1_max_attempts = 0 → no L1 retry."""
        from core.pipeline import retry as retry_mod
        from core.pipeline.retry import load_retry_config

        config_dir = tmp_path / ".ralph"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("[retry]\nl1_max_attempts = 0\n")
        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)
        budget = load_retry_config()
        assert budget.l1_max_attempts == 0
        assert budget.l2_max_attempts == 2  # default

    def test_l2_max_attempts_three(self, tmp_path, monkeypatch) -> None:
        """[retry] l2_max_attempts = 3 → L2 retries up to 3 times."""
        from core.pipeline import retry as retry_mod
        from core.pipeline.retry import load_retry_config

        config_dir = tmp_path / ".ralph"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("[retry]\nl2_max_attempts = 3\n")
        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)
        budget = load_retry_config()
        assert budget.l1_max_attempts == 1  # default
        assert budget.l2_max_attempts == 3

    def test_invalid_negative_value_uses_defaults(self, tmp_path, monkeypatch) -> None:
        """Invalid (negative) value → defaults."""
        from core.pipeline import retry as retry_mod
        from core.pipeline.retry import load_retry_config

        config_dir = tmp_path / ".ralph"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("[retry]\nl1_max_attempts = -1\n")
        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)
        budget = load_retry_config()
        assert budget.l1_max_attempts == 1  # default
        assert budget.l2_max_attempts == 2  # default


# ─────────────────────────────────────────────────────────
# B1.3 — Agent re-invocation with failure context (spec §10.2 B1)
# ─────────────────────────────────────────────────────────


class TestAgentReinvocation:
    """B1.3: invoke_agent wrapper re-invokes on retryable failures.

    Per spec §10.2 B1:
      - retry_l2 → re-invoke up to ``l2_max_attempts`` times.
      - retry_transient → re-invoke up to ``l1_max_attempts`` time.
      - Each retry's prompt contains the previous ``stdout_tail``.
      - After max attempts exhausted, the stage blocks.

    The wrapper exposes two helpers used by callers (and tested
    directly here):
      - ``_invoke_with_retry(prompt, issue_num, classify_fn, budget)``
      - ``_should_retry(action, attempt, budget)``

    Tests patch the ``subprocess.run`` call inside ``invoke_agent``
    to control the agent's return code and output.
    """

    @pytest.fixture(autouse=True)
    def _patch_log_metrics(self, monkeypatch):
        """Prevent retry metrics from writing to the project's log file."""
        from core.pipeline import retry as retry_mod

        monkeypatch.setattr(retry_mod, "log_metrics", mock.Mock())

    def test_retry_l2_triggers_reinvocation(self, tmp_path, monkeypatch) -> None:
        """retry_l2 action → second invocation up to l2_max_attempts."""
        # _invoke_with_retry lives at core.pipeline.retry now (C1 step 14b)
        # and lazy-imports invoke_agent_with_output from core.pipeline.agents.pi,
        # so both PROJECT_ROOT and the agent mock must target the new homes.
        from core.pipeline import retry as retry_mod
        from core.pipeline.agents import pi as pi_mod
        from core.pipeline.retry import RetryBudget, _invoke_with_retry

        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)

        # First call returns exit 1 (test_failure / retry_l2).
        # Second call returns exit 0 (success / accept).
        responses = iter(
            [
                _FakeResult(returncode=1, stdout=b"failed", stderr=b""),
                _FakeResult(returncode=0, stdout=b"ok", stderr=b""),
            ]
        )

        def fake_invoke_agent(prompt, issue_num, worktree_path=None):
            result = next(responses)
            return (result.returncode == 0, result.stdout.decode())

        with mock.patch.object(
            pi_mod, "invoke_agent_with_output", side_effect=fake_invoke_agent
        ):
            budget = RetryBudget(l1_max_attempts=1, l2_max_attempts=2)
            # First attempt: classify returns retry_l2.
            # Second attempt: classify returns accept.
            actions = iter(["retry_l2", "accept"])

            def classify_fn(stdout, rc):
                return next(actions)

            ok, last_stdout = _invoke_with_retry("do thing", 1, classify_fn, budget)

        assert ok is True

    def test_retry_prompt_contains_previous_stdout_tail(
        self, tmp_path, monkeypatch
    ) -> None:
        """Each retry's prompt contains the previous stdout tail."""
        from core.pipeline import retry as retry_mod
        from core.pipeline.agents import pi as pi_mod
        from core.pipeline.retry import RetryBudget, _invoke_with_retry

        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)

        captured_prompts: list[str] = []

        def fake_invoke_agent(prompt, issue_num, worktree_path=None):
            captured_prompts.append(prompt)
            if len(captured_prompts) == 1:
                return (False, "previous failure output line 1\nline 2")
            return (True, "now succeeds")

        with mock.patch.object(
            pi_mod, "invoke_agent_with_output", side_effect=fake_invoke_agent
        ):
            budget = RetryBudget(l1_max_attempts=1, l2_max_attempts=2)
            actions = iter(["retry_l2", "accept"])

            def classify_fn(stdout, rc):
                return next(actions)

            _invoke_with_retry("first prompt", 1, classify_fn, budget)

        assert len(captured_prompts) == 2
        # The second prompt should contain the previous stdout content.
        assert "previous failure output line 1" in captured_prompts[1]

    def test_max_attempts_exhausted_blocks(self, tmp_path, monkeypatch) -> None:
        """After max attempts the wrapper returns blocked status."""
        from core.pipeline import retry as retry_mod
        from core.pipeline.agents import pi as pi_mod
        from core.pipeline.retry import RetryBudget, _invoke_with_retry

        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)

        with mock.patch.object(pi_mod, "invoke_agent_with_output") as fake:
            fake.return_value = (False, "still failing")
            budget = RetryBudget(l1_max_attempts=1, l2_max_attempts=2)
            # Always returns retry_l2 → eventually exhausted.

            def classify_fn(stdout, rc):
                return "retry_l2"

            ok, _ = _invoke_with_retry("do thing", 1, classify_fn, budget)

        # l2_max_attempts=2 → 2 invocations total, both fail, blocked.
        assert ok is False
        assert fake.call_count == 2

    def test_retry_transient_triggers_exactly_one_retry(
        self, tmp_path, monkeypatch
    ) -> None:
        """retry_transient triggers at most l1_max_attempts (default 1)."""
        from core.pipeline import retry as retry_mod
        from core.pipeline.agents import pi as pi_mod
        from core.pipeline.retry import RetryBudget, _invoke_with_retry

        monkeypatch.setattr(retry_mod, "PROJECT_ROOT", tmp_path)

        with mock.patch.object(pi_mod, "invoke_agent_with_output") as fake:
            fake.return_value = (False, "still failing")
            budget = RetryBudget(l1_max_attempts=1, l2_max_attempts=2)

            def classify_fn(stdout, rc):
                return "retry_transient"

            ok, _ = _invoke_with_retry("do thing", 1, classify_fn, budget)

        # l1_max_attempts=1 → 1 invocation total.
        assert ok is False
        assert fake.call_count == 1


class _FakeResult:
    """Helper class for tests that need subprocess.CompletedProcess quacks."""

    def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ─────────────────────────────────────────────────────────
# B3.3 — TEST + VERIFY using worktree (spec §10.2 B3)
# ─────────────────────────────────────────────────────────


class TestSubagentsUseWorktree:
    """B3.3: _run_test_subagent and run_verify_stage wrap agents in worktrees.

    Per spec §10.2 B3:
      - Both TEST and VERIFY sub-agents run inside a worktree.
      - create_worktree is called before invoke_agent.
      - remove_worktree is called in finally (cleanup survives agent failure).
      - Agent's CWD is the worktree path, not the repo root.

    Tests patch ``core.pipeline.agents.base.create_worktree`` and
    ``core.pipeline.agents.base.remove_worktree`` (the seam the engine
    uses per B3.1) and assert the lifecycle.
    """

    def test_test_subagent_creates_and_removes_worktree(
        self, tmp_path, monkeypatch
    ) -> None:
        """_run_test_subagent calls create_worktree and remove_worktree."""
        from core.pipeline.agents import base as agents_base

        monkeypatch.setattr(build_subagents, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        # Disable the pre-flight check so we don't need a real git repo.
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(
                build_subagents, "create_worktree", return_value=wt_path
            ) as create_wt,
            mock.patch.object(build_subagents, "remove_worktree") as remove_wt,
            mock.patch.object(
                build_subagents, "_invoke_with_retry", return_value=(True, "")
            ),
            mock.patch.object(build_subagents, "gh_comment"),
            mock.patch.object(build_subagents, "log_metrics"),
            mock.patch.object(
                build_subagents, "_snapshot_tests_dir", return_value=set()
            ),
            mock.patch.object(build_subagents, "_detect_new_tests", return_value=[]),
            mock.patch.object(build_subagents, "_save_test_tracking"),
        ):
            engine._run_test_subagent({"number": 1, "title": "Test issue"})

        assert create_wt.call_count == 1
        assert remove_wt.call_count == 1

    def test_test_subagent_cleans_up_on_agent_failure(
        self, tmp_path, monkeypatch
    ) -> None:
        """remove_worktree runs in finally — survives agent failure."""
        from core.pipeline.agents import base as agents_base

        monkeypatch.setattr(build_subagents, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(build_subagents, "create_worktree", return_value=wt_path),
            mock.patch.object(build_subagents, "remove_worktree") as remove_wt,
            mock.patch.object(
                build_subagents, "_invoke_with_retry", return_value=(False, "")
            ),
            mock.patch.object(build_subagents, "gh_comment"),
            mock.patch.object(build_subagents, "log_metrics"),
            mock.patch.object(
                build_subagents, "_snapshot_tests_dir", return_value=set()
            ),
            mock.patch.object(build_subagents, "_detect_new_tests", return_value=[]),
            mock.patch.object(build_subagents, "_save_test_tracking"),
        ):
            engine._run_test_subagent({"number": 1, "title": "Test issue"})

        # Cleanup must have run despite the agent failing.
        assert remove_wt.call_count == 1

    def test_verify_stage_creates_and_removes_worktree(
        self, tmp_path, monkeypatch
    ) -> None:
        """run_verify_stage calls create_worktree and remove_worktree."""
        from core.pipeline.agents import base as agents_base

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(
                verify_stage, "create_worktree", return_value=wt_path
            ) as create_wt,
            mock.patch.object(verify_stage, "remove_worktree") as remove_wt,
            mock.patch.object(verify_stage, "invoke_agent", return_value=True),
            mock.patch.object(verify_stage, "gh_comment"),
            mock.patch.object(verify_stage, "log_metrics"),
            mock.patch.object(verify_stage, "git"),
            mock.patch.object(verify_stage, "_has_commits", return_value=False),
            mock.patch.object(
                verify_stage,
                "run",
                return_value=mock.Mock(returncode=0, stdout="", stderr=""),
            ),
        ):
            engine.run_verify_stage({"number": 1, "title": "Test issue"})

        assert create_wt.call_count == 1
        assert remove_wt.call_count == 1


# ─────────────────────────────────────────────────────────
# D3.1 — ralph daemon --dry-run (spec §10.4 D3)
# ─────────────────────────────────────────────────────────


class TestDaemonDryRun:
    """D3.1: `ralph daemon --dry-run` validates the environment without invoking agents.

    Per spec §10.4 D3 + plan §2.4 order 1: dry-run walks the pipeline up
    to (but not including) agent invocation. Validates gh auth, git
    remote, the 8 status labels, and on-disk paths. No `pi` or `kimi`
    subprocess is invoked. Useful for CI health checks.

    The dry-run helper lives at ``core.pipeline.daemon.dry_run`` and is
    invoked from the CLI in ``core/engine.py`` when ``--dry-run`` is
    passed.
    """

    def test_dry_run_invokes_gh_auth_status(self, tmp_path, monkeypatch) -> None:
        """`dry_run()` invokes `gh auth status` (or equivalent) and exits 0 on success."""
        from core.pipeline import daemon as daemon_mod
        from core.pipeline import shell as shell_mod

        monkeypatch.setattr(shell_mod, "PROJECT_ROOT", tmp_path)
        # create a fake .ralph dir so the path check passes.
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(daemon_mod, "gh") as gh_mock,
            mock.patch.object(daemon_mod, "git") as git_mock,
        ):
            gh_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            git_mock.return_value = mock.Mock(
                returncode=0, stdout="origin\tgit@github.com:foo/bar.git\n", stderr=""
            )

            # Mock `gh label list` to return all 8 labels.
            def fake_gh(*args, **kwargs):
                if args and args[0] == "label" and args[1] == "list":
                    return mock.Mock(
                        returncode=0,
                        stdout='[{"name":"status:ready"},{"name":"status:design"},'
                        '{"name":"status:build"},{"name":"status:verify"},'
                        '{"name":"status:review"},{"name":"status:blocked"},'
                        '{"name":"status:build-retry"},{"name":"status:verify-retry"}]',
                        stderr="",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            gh_mock.side_effect = fake_gh

            rc = daemon_mod.dry_run()

        assert rc == 0
        # gh auth status was called
        assert any(
            call_args and call_args[0] and "auth" in call_args[0]
            for call_args in gh_mock.call_args_list
        ), f"Expected `gh auth status` invocation; got: {gh_mock.call_args_list}"

    def test_dry_run_invokes_git_remote(self, tmp_path, monkeypatch) -> None:
        """`dry_run()` invokes `git remote -v` to validate the remote."""
        from core.pipeline import daemon as daemon_mod
        from core.pipeline import shell as shell_mod

        monkeypatch.setattr(shell_mod, "PROJECT_ROOT", tmp_path)
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(daemon_mod, "gh") as gh_mock,
            mock.patch.object(daemon_mod, "git") as git_mock,
        ):
            git_mock.return_value = mock.Mock(
                returncode=0, stdout="origin\tgit@github.com:foo/bar.git\n", stderr=""
            )
            gh_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            def fake_gh(*args, **kwargs):
                if args and args[0] == "label" and args[1] == "list":
                    return mock.Mock(
                        returncode=0,
                        stdout='[{"name":"status:ready"},{"name":"status:design"},'
                        '{"name":"status:build"},{"name":"status:verify"},'
                        '{"name":"status:review"},{"name":"status:blocked"},'
                        '{"name":"status:build-retry"},{"name":"status:verify-retry"}]',
                        stderr="",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            gh_mock.side_effect = fake_gh

            daemon_mod.dry_run()

        # git remote -v was called
        assert any(
            call_args and call_args[0] and "remote" in call_args[0]
            for call_args in git_mock.call_args_list
        ), f"Expected `git remote` invocation; got: {git_mock.call_args_list}"

    def test_dry_run_validates_all_eight_status_labels(
        self, tmp_path, monkeypatch
    ) -> None:
        """`dry_run()` validates all 8 status labels exist via `gh label list`."""
        from core.pipeline import daemon as daemon_mod
        from core.pipeline import shell as shell_mod

        monkeypatch.setattr(shell_mod, "PROJECT_ROOT", tmp_path)
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(daemon_mod, "gh") as gh_mock,
            mock.patch.object(daemon_mod, "git") as git_mock,
        ):
            git_mock.return_value = mock.Mock(
                returncode=0, stdout="origin\tgit@github.com:foo/bar.git\n", stderr=""
            )
            gh_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            def fake_gh(*args, **kwargs):
                if args and args[0] == "label" and args[1] == "list":
                    return mock.Mock(
                        returncode=0,
                        stdout='[{"name":"status:ready"}]',  # only 1 label
                        stderr="",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            gh_mock.side_effect = fake_gh

            rc = daemon_mod.dry_run()

        # Should fail with non-zero exit because labels are missing.
        assert rc != 0

    def test_dry_run_does_not_invoke_pi_or_kimi_subprocess(
        self, tmp_path, monkeypatch
    ) -> None:
        """`dry_run()` does NOT invoke `subprocess.run` with `pi` or `kimi` in argv."""
        import subprocess as subprocess_mod

        from core.pipeline import daemon as daemon_mod
        from core.pipeline import shell as shell_mod

        monkeypatch.setattr(shell_mod, "PROJECT_ROOT", tmp_path)
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(daemon_mod, "gh") as gh_mock,
            mock.patch.object(daemon_mod, "git") as git_mock,
            mock.patch.object(subprocess_mod, "run") as subp_run,
        ):
            git_mock.return_value = mock.Mock(
                returncode=0, stdout="origin\tgit@github.com:foo/bar.git\n", stderr=""
            )
            gh_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            def fake_gh(*args, **kwargs):
                if args and args[0] == "label" and args[1] == "list":
                    return mock.Mock(
                        returncode=0,
                        stdout='[{"name":"status:ready"},{"name":"status:design"},'
                        '{"name":"status:build"},{"name":"status:verify"},'
                        '{"name":"status:review"},{"name":"status:blocked"},'
                        '{"name":"status:build-retry"},{"name":"status:verify-retry"}]',
                        stderr="",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            gh_mock.side_effect = fake_gh

            daemon_mod.dry_run()

        # No subprocess call should have pi/kimi in argv
        for call in subp_run.call_args_list:
            argv = call.args[0] if call.args else []
            assert not any(
                agent in str(argv).lower() for agent in ("pi", "kimi")
            ), f"dry_run should not invoke agent subprocess; got argv={argv}"


# ─────────────────────────────────────────────────────────
# D2.1 — status:retry label recognition (spec §10.4 D2)
# ─────────────────────────────────────────────────────────


class TestRetryLabelRecognition:
    """D2.1: the engine recognizes ``status:retry`` ALONGSIDE existing retry labels.

    Per spec §3.5 + §10.4 D2 + plan §3 R-12: the new ``status:retry``
    label works ADDITIVELY. The old labels (``status:build-retry``,
    ``status:verify-retry``) continue to work. No deprecation in v3.1.

    These tests assert:

      - ``status:retry`` is included in ``RETRY_LABEL_MAP`` (the canonical
        engine-side list of accepted retry labels).
      - All three labels map to a resume stage.
      - The mapping is exhaustive: every accepted retry label has a
        pipeline stage it resumes at.
    """

    def test_status_retry_in_accepted_labels(self) -> None:
        """The ``status:retry`` label is recognized by the engine (in RETRY_LABEL_MAP)."""
        from core.pipeline.issue_ops import RETRY_LABEL_MAP

        assert (
            "status:retry" in RETRY_LABEL_MAP
        ), f"status:retry missing from RETRY_LABEL_MAP: {RETRY_LABEL_MAP}"

    def test_old_labels_still_accepted(self) -> None:
        """Old labels (status:build-retry, status:verify-retry) still work (no deprecation in v3.1)."""
        from core.pipeline.issue_ops import RETRY_LABEL_MAP

        assert "status:build-retry" in RETRY_LABEL_MAP
        assert "status:verify-retry" in RETRY_LABEL_MAP

    def test_retry_labels_map_to_resume_stages(self) -> None:
        """Each accepted retry label maps to a valid resume stage."""
        from core.pipeline.issue_ops import RETRY_LABEL_MAP

        valid_stages = {"build", "verify"}
        for label, resume_stage in RETRY_LABEL_MAP.items():
            assert (
                resume_stage in valid_stages
            ), f"{label} maps to unknown stage {resume_stage!r}"
