"""Tests for core.pipeline.stages.build_subagents (B3, Phase D follow-up)."""

from __future__ import annotations

from unittest import mock


class TestRunTestSubagentWorktreeHandling:
    """Worktree creation and teardown in the TEST sub-agent."""

    def test_worktree_failure_blocks_test_subagent(self, tmp_path, monkeypatch) -> None:
        """WorktreeError makes _run_test_subagent return False."""
        from core.pipeline.agents import base as agents_base
        from core.pipeline.stages import build_subagents as subagents_mod

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        from core.pipeline.agents.base import WorktreeError

        with (
            mock.patch.object(
                subagents_mod,
                "create_worktree",
                side_effect=WorktreeError("git worktree not available"),
            ) as create_wt,
            mock.patch.object(subagents_mod, "remove_worktree") as remove_wt,
            mock.patch.object(subagents_mod, "gh_comment") as comment,
            mock.patch.object(subagents_mod, "log_metrics") as log,
        ):
            from core.pipeline.stages.build_subagents import _run_test_subagent

            result = _run_test_subagent({"number": 1, "title": "Test"})

        assert result is False
        create_wt.assert_called_once_with(1)
        # No worktree created → remove_worktree should not be called.
        remove_wt.assert_not_called()
        # Should emit worktree_failed metric.
        assert any(
            call.args and call.args[0] == "worktree_failed"
            for call in log.call_args_list
        ), f"Expected worktree_failed metric; got {log.call_args_list}"
        # Should post a blocking comment.
        assert any(
            "blocked" in str(call.args[1]).lower() for call in comment.call_args_list
        ), f"Expected blocking comment; got {comment.call_args_list}"

    def test_worktree_removed_on_subagent_failure(self, tmp_path, monkeypatch) -> None:
        """When create_worktree succeeds, remove_worktree is called in finally."""
        from core.pipeline.agents import base as agents_base
        from core.pipeline.stages import build_subagents as subagents_mod

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(subagents_mod, "create_worktree", return_value=wt_path),
            mock.patch.object(subagents_mod, "remove_worktree") as remove_wt,
            mock.patch.object(
                subagents_mod, "_invoke_with_retry", return_value=(False, None)
            ) as invoke_retry,
            mock.patch.object(subagents_mod, "_snapshot_tests_dir", return_value={}),
            mock.patch.object(subagents_mod, "_save_test_tracking"),
            mock.patch.object(subagents_mod, "write_qa_tests"),
            mock.patch.object(subagents_mod, "gh_comment"),
        ):
            from core.pipeline.stages.build_subagents import _run_test_subagent

            result = _run_test_subagent({"number": 1, "title": "Test"})

        assert result is False
        remove_wt.assert_called_once_with(wt_path)
        invoke_retry.assert_called_once()
        _, kwargs = invoke_retry.call_args
        assert kwargs.get("worktree_path") == wt_path

    def test_worktree_path_passed_to_agent_invocation(
        self, tmp_path, monkeypatch
    ) -> None:
        """The created worktree path is forwarded to the agent invocation."""
        from core.pipeline.agents import base as agents_base
        from core.pipeline.stages import build_subagents as subagents_mod

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(subagents_mod, "create_worktree", return_value=wt_path),
            mock.patch.object(subagents_mod, "remove_worktree"),
            mock.patch.object(
                subagents_mod, "_invoke_with_retry", return_value=(True, "")
            ) as invoke_retry,
            mock.patch.object(subagents_mod, "_snapshot_tests_dir", return_value={}),
            mock.patch.object(subagents_mod, "_save_test_tracking"),
            mock.patch.object(subagents_mod, "write_qa_tests"),
            mock.patch.object(subagents_mod, "gh_comment"),
        ):
            from core.pipeline.stages.build_subagents import _run_test_subagent

            _run_test_subagent({"number": 1, "title": "Test"})

        _, kwargs = invoke_retry.call_args
        assert kwargs.get("worktree_path") == wt_path
