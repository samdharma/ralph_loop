"""Tests for core.pipeline.agents.base (C1.5a)."""

from __future__ import annotations


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
