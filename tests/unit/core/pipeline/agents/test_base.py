"""Tests for core.pipeline.agents.base (C1.5a, D1.2)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock


class TestAgentBaseAtNewPath:
    """C1.5a: AgentBase class at new location (in addition to worktree helpers)."""

    def test_agent_base_importable(self) -> None:
        from core.pipeline.agents.base import AgentBase

        assert AgentBase is not None

    def test_worktree_helpers_still_present(self) -> None:
        """Regression guard for B3.1 (worktree helpers from B-019)."""
        from core.pipeline.agents.base import (
            create_worktree,
            remove_worktree,
        )

        assert callable(create_worktree)
        assert callable(remove_worktree)

    def test_agent_base_defines_abstract_invoke(self) -> None:
        from core.pipeline.agents.base import AgentBase

        # Should have an abstract method named 'invoke'.
        assert hasattr(AgentBase, "invoke")
        assert callable(AgentBase.invoke)


# ─────────────────────────────────────────────────────────
# D1.2 — Worktree-merge logic (spec §10.4 D1)
# ─────────────────────────────────────────────────────────


class TestMergeWorktrees:
    """D1.2: merge two worktrees (TEST + IMPLEMENT) per the path-domain policy.

    Per spec §10.4 D1 + plan §3 R-8:

      - ``tests/`` conflicts → TEST wins.
      - ``src/`` conflicts → IMPLEMENT wins.
      - Off-domain overlaps → :class:`OverlapError` (FAIL FAST).

    The merge helper takes the two worktree paths plus a base ref
    and returns the path to the merged tree. Tests mock
    ``_run_git`` so the seam the engine uses to invoke
    ``git diff`` / ``git merge`` is fully observable.
    """

    def test_merge_worktrees_is_callable(self) -> None:
        """``merge_worktrees`` is exposed from ``core.pipeline.agents.base``."""
        from core.pipeline.agents.base import merge_worktrees

        assert callable(merge_worktrees)

    def test_non_overlapping_worktrees_merge_cleanly(
        self, tmp_path, monkeypatch
    ) -> None:
        """Non-overlapping worktrees (TEST wrote tests/, IMPLEMENT wrote src/) merge without raising."""
        from core.pipeline.agents import base as agents_base

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)

        test_wt = tmp_path / "wt-test"
        impl_wt = tmp_path / "wt-impl"
        test_wt.mkdir()
        impl_wt.mkdir()

        # git diff --name-only: empty output (no overlap)
        with mock.patch.object(
            agents_base, "_run_git"
        ) as run_git:
            run_git.return_value = mock.Mock(
                returncode=0, stdout=b"", stderr=b""
            )
            from core.pipeline.agents.base import merge_worktrees

            # Should not raise.
            result = merge_worktrees(test_wt, impl_wt, base="HEAD")
            assert result is not None

    def test_tests_conflict_test_wins(self, tmp_path, monkeypatch) -> None:
        """When a ``tests/`` file conflicts, TEST wins."""
        from core.pipeline.agents import base as agents_base

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)

        test_wt = tmp_path / "wt-test"
        impl_wt = tmp_path / "wt-impl"
        test_wt.mkdir()
        impl_wt.mkdir()

        # Simulate: tests/file.py differs between worktrees.
        # We mock _run_git to:
        #   - diff --name-only → returns "tests/file.py\n"
        #   - merge -X ours -- tests/ → succeeds
        #   - merge -X theirs -- src/ → succeeds (no-op)
        call_log: list[tuple] = []

        def fake_git(argv):
            call_log.append(tuple(argv))
            if "diff" in argv and "--name-only" in argv:
                return mock.Mock(
                    returncode=0,
                    stdout=b"tests/unit/test_qa.py\n",
                    stderr=b"",
                )
            # git merge invocations succeed.
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with mock.patch.object(agents_base, "_run_git", side_effect=fake_git):
            from core.pipeline.agents.base import merge_worktrees

            result = merge_worktrees(test_wt, impl_wt, base="HEAD")
            assert result is not None

        # At least one merge was invoked with -X ours (TEST wins).
        ours_calls = [
            argv for argv in call_log if "-X" in argv and "ours" in argv
        ]
        assert ours_calls, f"Expected `git merge -X ours` for tests/; got {call_log}"

    def test_src_conflict_implement_wins(self, tmp_path, monkeypatch) -> None:
        """When a ``src/`` file conflicts, IMPLEMENT wins."""
        from core.pipeline.agents import base as agents_base

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)

        test_wt = tmp_path / "wt-test"
        impl_wt = tmp_path / "wt-impl"
        test_wt.mkdir()
        impl_wt.mkdir()

        call_log: list[tuple] = []

        def fake_git(argv):
            call_log.append(tuple(argv))
            if "diff" in argv and "--name-only" in argv:
                return mock.Mock(
                    returncode=0,
                    stdout=b"src/feature.py\n",
                    stderr=b"",
                )
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with mock.patch.object(agents_base, "_run_git", side_effect=fake_git):
            from core.pipeline.agents.base import merge_worktrees

            result = merge_worktrees(test_wt, impl_wt, base="HEAD")
            assert result is not None

        # At least one merge was invoked with -X theirs (IMPLEMENT wins).
        theirs_calls = [
            argv for argv in call_log if "-X" in argv and "theirs" in argv
        ]
        assert theirs_calls, f"Expected `git merge -X theirs` for src/; got {call_log}"

    def test_offdomain_conflict_raises_overlap_error(
        self, tmp_path, monkeypatch
    ) -> None:
        """Off-domain overlap (e.g., docs/) raises :class:`OverlapError` (FAIL FAST)."""
        from core.pipeline.agents import base as agents_base

        monkeypatch.setattr(agents_base, "PROJECT_ROOT", tmp_path)

        test_wt = tmp_path / "wt-test"
        impl_wt = tmp_path / "wt-impl"
        test_wt.mkdir()
        impl_wt.mkdir()

        def fake_git(argv):
            if "diff" in argv and "--name-only" in argv:
                # Overlap in docs/ — neither TEST nor IMPLEMENT domain.
                return mock.Mock(
                    returncode=0,
                    stdout=b"docs/spec.md\n",
                    stderr=b"",
                )
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with mock.patch.object(agents_base, "_run_git", side_effect=fake_git):
            from core.pipeline.agents.base import OverlapError, merge_worktrees

            with __import__("pytest").raises(OverlapError) as exc_info:
                merge_worktrees(test_wt, impl_wt, base="HEAD")

            # Error message names the offending file.
            assert "docs/spec.md" in str(exc_info.value)
