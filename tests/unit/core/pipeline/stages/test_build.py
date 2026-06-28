"""Tests for core.pipeline.stages.build (C1.4b, D1.1)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock


class TestBuildStageAtNewPath:
    """C1.4b: BUILD stage at new location."""

    def test_build_stage_importable(self) -> None:
        from core.pipeline.stages.build import BuildStage

        assert BuildStage is not None

    def test_build_stage_inherits_from_stage(self) -> None:
        from core.pipeline.stages.base import Stage
        from core.pipeline.stages.build import BuildStage

        assert issubclass(BuildStage, Stage)

    def test_build_stage_name_is_build(self) -> None:
        from core.pipeline.stages.build import BuildStage

        assert BuildStage.name == "build"

    def test_build_stage_run_is_callable(self) -> None:
        from core.pipeline.stages.build import BuildStage

        stage = BuildStage()
        assert callable(stage.run)


# ─────────────────────────────────────────────────────────
# D1.1 — Parallel TEST + IMPLEMENT scheduler (spec §10.4 D1)
# ─────────────────────────────────────────────────────────


class TestParallelScheduler:
    """D1.1: parallel TEST + IMPLEMENT scheduler.

    Per spec §10.4 D1 + plan §3 R-8 mitigation: ship behind
    ``RALPH_PARALLEL_BUILD=true`` config flag (default false). When
    enabled, the scheduler creates two git worktrees, runs TEST in
    one and IMPLEMENT in the other concurrently, and merges the
    results per the path-domain policy (D1.2 / D1.3).

    Default (flag false) → sequential execution (single worktree).
    Flag true → parallel execution (two worktrees).
    """

    def test_default_flag_is_sequential(self, tmp_path, monkeypatch) -> None:
        """Default (flag unset / false) → sequential execution (single worktree)."""
        from core.pipeline.stages import build as build_mod

        config_dir = tmp_path / ".ralph"
        config_dir.mkdir(parents=True, exist_ok=True)
        # No config file → defaults.

        # The flag reader must report False when env is unset and
        # config has no ``[performance] parallel_build`` key.
        monkeypatch.delenv("RALPH_PARALLEL_BUILD", raising=False)
        monkeypatch.setattr(build_mod, "PROJECT_ROOT", tmp_path)

        from core.pipeline.stages.build import _is_parallel_build_enabled

        assert _is_parallel_build_enabled() is False

    def test_env_flag_true_enables_parallel(self, monkeypatch) -> None:
        """``RALPH_PARALLEL_BUILD=true`` enables parallel mode."""
        from core.pipeline.stages import build as build_mod

        monkeypatch.setenv("RALPH_PARALLEL_BUILD", "true")
        from core.pipeline.stages.build import _is_parallel_build_enabled

        assert _is_parallel_build_enabled() is True

    def test_config_flag_true_enables_parallel(self, tmp_path, monkeypatch) -> None:
        """``.ralph/config.toml [performance] parallel_build = true`` enables parallel mode."""
        from core.pipeline.stages import build as build_mod

        config_dir = tmp_path / ".ralph"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.toml").write_text(
            "[performance]\nparallel_build = true\n"
        )
        monkeypatch.delenv("RALPH_PARALLEL_BUILD", raising=False)
        monkeypatch.setattr(build_mod, "PROJECT_ROOT", tmp_path)

        from core.pipeline.stages.build import _is_parallel_build_enabled

        assert _is_parallel_build_enabled() is True

    def test_parallel_mode_creates_two_worktrees(self, tmp_path, monkeypatch) -> None:
        """When parallel is enabled, the scheduler creates 2 worktrees (test + implement)."""
        from core.pipeline.stages import build as build_mod
        from core.pipeline.agents import base as agents_base

        monkeypatch.setenv("RALPH_PARALLEL_BUILD", "true")
        monkeypatch.setattr(build_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)
        # Disable the pre-flight check so we don't need a real git repo.
        monkeypatch.setattr(agents_base, "_preflight_check", lambda: None)

        test_wt = tmp_path / ".ralph" / "worktrees" / "1-test"
        impl_wt = tmp_path / ".ralph" / "worktrees" / "1-impl"
        test_wt.mkdir(parents=True, exist_ok=True)
        impl_wt.mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(
                build_mod,
                "create_worktree",
                side_effect=[test_wt, impl_wt],
            ) as create_wt,
            mock.patch.object(
                build_mod,
                "remove_worktree",
            ) as remove_wt,
        ):
            # Verify the parallel scheduler makes 2 create_worktree
            # calls (1 for test, 1 for implement).
            from core.pipeline.stages.build import (
                _parallel_create_worktrees,
            )

            wt_test, wt_impl = _parallel_create_worktrees(1)

        assert create_wt.call_count == 2
        assert wt_test == test_wt
        assert wt_impl == impl_wt
