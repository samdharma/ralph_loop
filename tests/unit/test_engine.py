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

    def test_qa_test_files_have_mode_0444_after_subagent_returns(self, tmp_path, monkeypatch) -> None:
        """After _run_test_subagent returns successfully, every file in QA test dir has mode 0o444."""
        qa_file = self._setup_qa_test_file(tmp_path)

        # Force PROJECT_ROOT to tmp_path so .ralph/ and tests/ resolve correctly.
        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)

        # Mock all side-effecting helpers + the agent invocation.
        with mock.patch.object(engine, "invoke_agent", return_value=True), \
             mock.patch.object(engine, "gh_comment"), \
             mock.patch.object(engine, "log_metrics"), \
             mock.patch.object(engine, "_snapshot_tests_dir") as mock_snap, \
             mock.patch.object(engine, "_detect_new_tests", return_value=[str(qa_file.relative_to(tmp_path))]), \
             mock.patch.object(engine, "_save_test_tracking"):
            issue = {"number": 1, "title": "Test issue"}
            ok = engine._run_test_subagent(issue)

        assert ok is True
        mode = qa_file.stat().st_mode & 0o777
        assert mode == 0o444, f"Expected mode 0o444, got {oct(mode)}"

    def test_implement_cannot_write_to_locked_qa_test(self, tmp_path, monkeypatch) -> None:
        """IMPLEMENT sub-agent attempting to write to a QA test file raises PermissionError."""
        qa_file = self._setup_qa_test_file(tmp_path)
        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)

        with mock.patch.object(engine, "invoke_agent", return_value=True), \
             mock.patch.object(engine, "gh_comment"), \
             mock.patch.object(engine, "log_metrics"), \
             mock.patch.object(engine, "_snapshot_tests_dir"), \
             mock.patch.object(engine, "_detect_new_tests", return_value=[str(qa_file.relative_to(tmp_path))]), \
             mock.patch.object(engine, "_save_test_tracking"):
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
        monkeypatch.setattr(engine, "PROJECT_ROOT", tmp_path)

        observed_modes: list[int] = []

        def fake_invoke_agent(prompt, issue_num):
            # Snapshot the file mode WHILE the agent is running.
            observed_modes.append(qa_file.stat().st_mode & 0o777)
            return True

        with mock.patch.object(engine, "invoke_agent", side_effect=fake_invoke_agent), \
             mock.patch.object(engine, "gh_comment"), \
             mock.patch.object(engine, "log_metrics"), \
             mock.patch.object(engine, "_snapshot_tests_dir"), \
             mock.patch.object(engine, "_detect_new_tests", return_value=[str(qa_file.relative_to(tmp_path))]), \
             mock.patch.object(engine, "_save_test_tracking"):
            engine._run_test_subagent({"number": 1, "title": "Test issue"})

        # During the agent run, the file should NOT yet be locked.
        assert len(observed_modes) == 1
        assert observed_modes[0] != 0o444, "File was locked BEFORE agent returned"

        # After the agent returned, the file IS locked.
        final_mode = qa_file.stat().st_mode & 0o777
        assert final_mode == 0o444


def _make_gh_response(number=42, state="OPEN", body=""):
    return json.dumps(
        {"number": number, "title": "Test issue", "body": body, "state": state}
    )


def test_fetch_issue_by_number_returns_open_issue():
    """fetch_issue_by_number returns an open issue with no unmet deps."""
    with mock.patch.object(
        engine, "gh", return_value=mock.Mock(stdout=_make_gh_response())
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
        engine, "gh", return_value=mock.Mock(stdout=_make_gh_response(state="CLOSED"))
    ):
        issue = engine.fetch_issue_by_number(42)

    assert issue is None


def test_fetch_issue_by_number_returns_none_when_not_found():
    """fetch_issue_by_number returns None if gh issue view fails."""
    import subprocess

    with mock.patch.object(
        engine, "gh", side_effect=subprocess.CalledProcessError(1, "gh")
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

    with mock.patch.object(engine, "gh", side_effect=fake_gh):
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

    with mock.patch.object(engine, "gh", side_effect=fake_gh):
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

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        snapshot = engine._snapshot_tests_dir()

    assert list(snapshot.keys()) == ["tests/unit/test_real.py"]


# ─────────────────────────────────────────────────────────
# Test tracking sanitization (#56, #57)
# ─────────────────────────────────────────────────────────


def test_save_test_tracking_sanitizes_pycache_paths(tmp_path):
    """_save_test_tracking excludes __pycache__ and .pyc entries."""
    fake_project = tmp_path / "project"
    ralph_dir = fake_project / ".ralph"

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
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

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
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

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
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

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
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

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        result = engine._resolve_existing_test_paths([
            "tests/unit/test_real.py",
            "tests/unit/test_gone.py",
            "tests/unit/test_also_missing.py",
        ])

    assert result == ["tests/unit/test_real.py"]


def test_resolve_existing_test_paths_returns_empty_for_all_missing(tmp_path):
    """_resolve_existing_test_paths returns empty list when no paths exist."""
    fake_project = tmp_path / "project"
    fake_project.mkdir(parents=True)

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        result = engine._resolve_existing_test_paths([
            "tests/unit/ghost.py",
            "tests/integration/nope.py",
        ])

    assert result == []


def test_resolve_existing_test_paths_returns_empty_for_empty_input(tmp_path):
    """_resolve_existing_test_paths handles empty input gracefully."""
    fake_project = tmp_path / "project"
    fake_project.mkdir(parents=True)

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        result = engine._resolve_existing_test_paths([])

    assert result == []


def test_snapshot_file_hashes_returns_hashes_for_existing_files(tmp_path):
    """_snapshot_file_hashes returns content hashes for files that exist."""
    fake_project = tmp_path / "project"
    tests_dir = fake_project / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_a.py").write_text("def test(): pass\n")
    (tests_dir / "test_b.py").write_text("def test(): assert True\n")

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        hashes = engine._snapshot_file_hashes([
            "tests/unit/test_a.py",
            "tests/unit/test_b.py",
            "tests/unit/test_missing.py",
        ])

    assert len(hashes) == 2
    assert "tests/unit/test_a.py" in hashes
    assert "tests/unit/test_b.py" in hashes
    assert "tests/unit/test_missing.py" not in hashes


def test_snapshot_file_hashes_returns_empty_for_all_missing(tmp_path):
    """_snapshot_file_hashes skips missing files, returns empty dict."""
    fake_project = tmp_path / "project"
    fake_project.mkdir(parents=True)

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        hashes = engine._snapshot_file_hashes(["tests/nowhere.py"])

    assert hashes == {}


def test_detect_tampered_tests_finds_changed_files(tmp_path):
    """_detect_tampered_tests returns files whose content hash changed."""
    fake_project = tmp_path / "project"
    tests_dir = fake_project / "tests" / "unit"
    tests_dir.mkdir(parents=True)

    test_file = tests_dir / "test_x.py"
    test_file.write_text("def test(): pass\n")

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        before = engine._snapshot_file_hashes(["tests/unit/test_x.py"])

    # Modify the file
    test_file.write_text("def test(): assert False\n")

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        after = engine._snapshot_file_hashes(["tests/unit/test_x.py"])
        tampered = engine._detect_tampered_tests(before, after)

    assert tampered == ["tests/unit/test_x.py"]


def test_detect_tampered_tests_returns_empty_when_unchanged(tmp_path):
    """_detect_tampered_tests returns empty when files haven't changed."""
    fake_project = tmp_path / "project"
    tests_dir = fake_project / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_x.py").write_text("def test(): pass\n")

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        before = engine._snapshot_file_hashes(["tests/unit/test_x.py"])
        after = engine._snapshot_file_hashes(["tests/unit/test_x.py"])
        tampered = engine._detect_tampered_tests(before, after)

    assert tampered == []


def test_detect_tampered_tests_ignores_new_files(tmp_path):
    """_detect_tampered_tests only reports modified files, not new ones."""
    fake_project = tmp_path / "project"
    tests_dir = fake_project / "tests" / "unit"
    tests_dir.mkdir(parents=True)

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        before: dict[str, str] = {}
    
    (tests_dir / "test_new.py").write_text("def test(): pass\n")

    with mock.patch.object(engine, "PROJECT_ROOT", fake_project):
        after = engine._snapshot_file_hashes(["tests/unit/test_new.py"])
        tampered = engine._detect_tampered_tests(before, after)

    # New files are NOT tampered (they didn't exist before)
    assert tampered == []


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
        returncode=1, stdout="", stderr="APIProviderRateLimitError: 429"
    )
    with mock.patch.object(
        engine, "_resolve_agent_binary", return_value="kimi"
    ), mock.patch.object(engine, "run", return_value=fake_result):
        with pytest.raises(engine.ProviderRateLimitError):
            engine.invoke_agent("prompt", 42)


def test_invoke_agent_raises_quota_error_on_pi_limit():
    """invoke_agent raises ProviderQuotaError when output contains quota message."""
    fake_result = mock.Mock(
        returncode=1, stdout="", stderr="FreeUsageLimitError: quota exceeded"
    )
    with mock.patch.object(
        engine, "_resolve_agent_binary", return_value="pi"
    ), mock.patch.object(engine, "run", return_value=fake_result):
        with pytest.raises(engine.ProviderQuotaError):
            engine.invoke_agent("prompt", 42)


def test_find_alternate_agent_returns_other_available_agent():
    """_find_alternate_agent returns the other agent when it is on PATH."""

    def fake_which(cmd):
        return mock.Mock(
            returncode=0 if cmd[0] == "which" and cmd[1] in ("kimi", "pi") else 1
        )

    with mock.patch.object(engine, "subprocess") as mock_subp:
        mock_subp.run.side_effect = lambda cmd, **kw: fake_which(cmd)
        # Current agent is kimi, so alternate is pi.
        assert engine._find_alternate_agent({"kimi"}) == "pi"
        # Current agent is pi, so alternate is kimi.
        assert engine._find_alternate_agent({"pi"}) == "kimi"


def test_find_alternate_agent_returns_none_when_no_other_agent():
    """_find_alternate_agent returns None when the other agent is not installed."""

    def fake_which(cmd):
        # Only kimi is available.
        return mock.Mock(returncode=0 if cmd == ["which", "kimi"] else 1)

    with mock.patch.object(engine, "subprocess") as mock_subp:
        mock_subp.run.side_effect = lambda cmd, **kw: fake_which(cmd)
        assert engine._find_alternate_agent({"kimi"}) is None


def _make_sleep_shutdown():
    """Return a side-effect that sets the shutdown flag on the first sleep call."""
    called = False

    def _sleep(seconds):
        nonlocal called
        if not called:
            called = True
            engine._shutdown_requested = True

    return _sleep


def test_run_loop_reverts_ready_and_sleeps_on_rate_limit():
    """A provider rate-limit pauses the loop, reverts the ticket to ready, and does not block it."""
    engine._shutdown_requested = False
    engine._in_cleanup = False
    os.environ.pop("RALPH_AGENT", None)
    issue = {"number": 42, "title": "Test"}

    with mock.patch.object(
        engine, "acquire_pid_file", return_value=True
    ), mock.patch.object(
        engine, "recover_from_crash", return_value=None
    ), mock.patch.object(
        engine, "fetch_ready_ticket", side_effect=[issue, None]
    ), mock.patch.object(
        engine, "transition_label"
    ) as mock_transition, mock.patch.object(
        engine, "run_pipeline", side_effect=engine.ProviderRateLimitError("429")
    ), mock.patch.object(
        engine, "_find_alternate_agent", return_value=None
    ), mock.patch.object(
        engine, "_revert_to_ready"
    ) as mock_revert, mock.patch.object(
        engine, "time"
    ) as mock_time, mock.patch.object(
        engine, "gh", return_value=mock.Mock(stdout="[]")
    ), mock.patch.object(
        engine, "sync_status"
    ), mock.patch.object(
        engine, "gh_comment"
    ), mock.patch.object(
        engine, "log_metrics"
    ), mock.patch.object(
        engine, "release_pid_file"
    ):
        mock_time.sleep.side_effect = _make_sleep_shutdown()
        engine.run_loop()

    # Claimed to design, then reverted to ready.
    mock_transition.assert_any_call(42, "status:design", "status:ready")
    mock_revert.assert_called_once_with(42)
    # Rate-limit backoff uses 1-second interruptible sleeps.
    mock_time.sleep.assert_any_call(1)


def test_run_loop_falls_back_to_alternate_agent():
    """When the current agent is rate-limited, the loop tries the alternate agent once."""
    engine._shutdown_requested = False
    engine._in_cleanup = False
    os.environ.pop("RALPH_AGENT", None)
    issue = {"number": 42, "title": "Test"}
    calls = []

    def fail_then_succeed(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise engine.ProviderRateLimitError("429")
        return True

    def fetch_gen():
        # First claim (with original agent), then re-claim after fallback.
        yield issue
        yield issue
        engine._shutdown_requested = True
        while True:
            yield None

    with mock.patch.object(
        engine, "acquire_pid_file", return_value=True
    ), mock.patch.object(
        engine, "recover_from_crash", return_value=None
    ), mock.patch.object(
        engine, "fetch_ready_ticket", side_effect=fetch_gen()
    ), mock.patch.object(
        engine, "transition_label"
    ) as mock_transition, mock.patch.object(
        engine, "run_pipeline", side_effect=fail_then_succeed
    ), mock.patch.object(
        engine, "_find_alternate_agent", return_value="pi"
    ), mock.patch.object(
        engine, "_revert_to_ready"
    ) as mock_revert, mock.patch.object(
        engine, "time"
    ), mock.patch.object(
        engine, "gh", return_value=mock.Mock(stdout="[]")
    ), mock.patch.object(
        engine, "sync_status"
    ), mock.patch.object(
        engine, "gh_comment"
    ), mock.patch.object(
        engine, "log_metrics"
    ), mock.patch.object(
        engine, "release_pid_file"
    ):
        engine.run_loop()

    # Reverted to ready before retrying with alternate agent.
    mock_revert.assert_called_once_with(42)
    # Re-claimed for the fallback attempt.
    assert mock_transition.call_count >= 2
    assert os.environ.get("RALPH_AGENT") == "pi"


def test_run_loop_creates_project_issue_when_all_agents_exhausted():
    """When all agents hit quota/rate-limit, the loop logs a project issue and stops."""
    engine._shutdown_requested = False
    engine._in_cleanup = False
    os.environ.pop("RALPH_AGENT", None)
    issue = {"number": 42, "title": "Test"}

    with mock.patch.object(
        engine, "acquire_pid_file", return_value=True
    ), mock.patch.object(
        engine, "recover_from_crash", return_value=None
    ), mock.patch.object(
        engine, "fetch_ready_ticket", side_effect=[issue, None]
    ), mock.patch.object(
        engine, "transition_label"
    ), mock.patch.object(
        engine, "run_pipeline", side_effect=engine.ProviderQuotaError("quota")
    ), mock.patch.object(
        engine, "_find_alternate_agent", return_value=None
    ), mock.patch.object(
        engine, "_revert_to_ready"
    ), mock.patch.object(
        engine, "_create_provider_issue"
    ) as mock_create, mock.patch.object(
        engine, "time"
    ), mock.patch.object(
        engine, "gh", return_value=mock.Mock(stdout="[]")
    ), mock.patch.object(
        engine, "sync_status"
    ), mock.patch.object(
        engine, "gh_comment"
    ), mock.patch.object(
        engine, "log_metrics"
    ), mock.patch.object(
        engine, "release_pid_file"
    ):
        engine.run_loop()

    mock_create.assert_called_once()
