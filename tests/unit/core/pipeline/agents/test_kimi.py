"""Tests for core.pipeline.agents.kimi (C1.5c)."""

from __future__ import annotations


class TestKimiAgentAtNewPath:
    """C1.5c: kimi agent wrapper at new location."""

    def test_kimi_agent_importable(self) -> None:
        from core.pipeline.agents.kimi import KimiAgent

        assert KimiAgent is not None

    def test_kimi_agent_inherits_agent_base(self) -> None:
        from core.pipeline.agents.base import AgentBase
        from core.pipeline.agents.kimi import KimiAgent

        assert issubclass(KimiAgent, AgentBase)

    def test_kimi_agent_name(self) -> None:
        from core.pipeline.agents.kimi import KimiAgent

        assert KimiAgent.name == "kimi"

    def test_kimi_agent_invoke_callable(self) -> None:
        from core.pipeline.agents.kimi import KimiAgent

        agent = KimiAgent()
        assert callable(agent.invoke)
