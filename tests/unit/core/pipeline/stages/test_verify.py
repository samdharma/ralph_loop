"""Tests for core.pipeline.stages.verify (C1.4c)."""

from __future__ import annotations

from unittest import mock


class TestVerifyStageAtNewPath:
    """C1.4c: VERIFY stage at new location."""

    def test_verify_stage_importable(self) -> None:
        from core.pipeline.stages.verify import VerifyStage

        assert VerifyStage is not None

    def test_verify_stage_inherits_from_stage(self) -> None:
        from core.pipeline.stages.base import Stage
        from core.pipeline.stages.verify import VerifyStage

        assert issubclass(VerifyStage, Stage)

    def test_verify_stage_name_is_verify(self) -> None:
        from core.pipeline.stages.verify import VerifyStage

        assert VerifyStage.name == "verify"

    def test_verify_stage_run_is_callable(self) -> None:
        from core.pipeline.stages.verify import VerifyStage

        stage = VerifyStage()
        assert callable(stage.run)

    def test_worktree_failure_blocks_verify(self, tmp_path, monkeypatch) -> None:
        """WorktreeError during create_worktree makes run_verify_stage return False."""
        from core.pipeline.agents import base as agents_base
        from core.pipeline.stages import verify as verify_mod

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        from core.pipeline.agents.base import WorktreeError

        with (
            mock.patch.object(
                verify_mod,
                "create_worktree",
                side_effect=WorktreeError("git worktree not available"),
            ) as create_wt,
            mock.patch.object(verify_mod, "remove_worktree") as remove_wt,
            mock.patch.object(verify_mod, "gh_comment") as comment,
            mock.patch.object(verify_mod, "log_metrics") as log,
        ):
            from core.pipeline.stages.verify import run_verify_stage

            result = run_verify_stage({"number": 1, "title": "Test"})

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

    def test_worktree_removed_on_success(self, tmp_path, monkeypatch) -> None:
        """When create_worktree succeeds, remove_worktree is called in finally."""
        from core.pipeline.agents import base as agents_base
        from core.pipeline.stages import verify as verify_mod

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        wt_path = tmp_path / ".ralph" / "worktrees" / "1"
        wt_path.mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(verify_mod, "create_worktree", return_value=wt_path),
            mock.patch.object(verify_mod, "remove_worktree") as remove_wt,
            mock.patch.object(verify_mod, "invoke_agent", return_value=True),
            mock.patch.object(verify_mod, "gh") as gh,
            mock.patch.object(verify_mod, "_has_commits", return_value=False),
        ):
            # Provide a comments response so the verdict check doesn't blow up.
            gh.return_value = mock.Mock(stdout='"## Overall: PASS"')
            # Patch validation gate to avoid running real tests.
            with mock.patch.object(
                verify_mod, "run", return_value=mock.Mock(returncode=0)
            ):
                from core.pipeline.stages.verify import run_verify_stage

                result = run_verify_stage({"number": 1, "title": "Test"})

        assert result is True
        remove_wt.assert_called_once_with(wt_path)
