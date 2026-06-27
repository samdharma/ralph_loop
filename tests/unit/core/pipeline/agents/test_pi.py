"""Tests for core.pipeline.agents.pi (C1.5b)."""

from __future__ import annotations


class TestPiAgentAtNewPath:
    """C1.5b: pi agent wrapper at new location."""

    def test_pi_agent_importable(self) -> None:
        from core.pipeline.agents.pi import PiAgent

        assert PiAgent is not None

    def test_pi_agent_inherits_agent_base(self) -> None:
        from core.pipeline.agents.base import AgentBase
        from core.pipeline.agents.pi import PiAgent

        assert issubclass(PiAgent, AgentBase)

    def test_pi_agent_name(self) -> None:
        from core.pipeline.agents.pi import PiAgent

        assert PiAgent.name == "pi"

    def test_pi_agent_invoke_callable(self) -> None:
        from core.pipeline.agents.pi import PiAgent

        agent = PiAgent()
        assert callable(agent.invoke)
