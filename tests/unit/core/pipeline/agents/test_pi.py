"""Tests for core.pipeline.agents.pi (C1.5b)."""

from __future__ import annotations

from unittest import mock


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


class TestInvokeAgentWithOutput:
    """Tests for the retry-aware agent invocation helper."""

    def test_subprocess_exception_returns_error_tuple(self, monkeypatch) -> None:
        """A missing binary must return an error tuple, not raise NameError.

        Regression: ProviderRateLimitError/ProviderQuotaError were imported
        inside the ``if result.returncode != 0`` block, so an early exception
        (e.g. FileNotFoundError) caused the function-level ``except`` tuple to
        raise NameError instead of catching it.
        """
        from core.pipeline.agents import pi as pi_mod

        monkeypatch.setattr(pi_mod, "_resolve_agent_binary", lambda: "pi")
        monkeypatch.setattr(
            pi_mod,
            "_run_agent",
            mock.Mock(side_effect=FileNotFoundError("no such file")),
        )

        ok, stdout = pi_mod.invoke_agent_with_output("prompt", 1)

        assert ok is False
        assert "agent invocation error" in stdout
        assert "no such file" in stdout

    def test_output_is_printed_and_returned(self, capsys, monkeypatch) -> None:
        """Captured stdout/stderr are echoed to the terminal and returned."""
        from core.pipeline.agents import pi as pi_mod

        monkeypatch.setattr(pi_mod, "_resolve_agent_binary", lambda: "pi")
        fake_result = mock.Mock(
            returncode=0,
            stdout=b"stdout line\n",
            stderr=b"stderr line\n",
        )
        monkeypatch.setattr(pi_mod, "_run_agent", mock.Mock(return_value=fake_result))

        ok, stdout = pi_mod.invoke_agent_with_output("prompt", 1)

        assert ok is True
        assert "stdout line" in stdout
        assert "stderr line" in stdout
        captured = capsys.readouterr()
        assert "stdout line" in captured.out
        assert "stderr line" in captured.err

    def test_worktree_path_is_passed_to_run_agent(self, monkeypatch, tmp_path) -> None:
        """When a worktree path is given, _run_agent receives cwd=worktree_path."""
        from core.pipeline.agents import pi as pi_mod

        monkeypatch.setattr(pi_mod, "_resolve_agent_binary", lambda: "pi")
        run_agent_spy = mock.Mock(
            return_value=mock.Mock(returncode=0, stdout=b"", stderr=b"")
        )
        monkeypatch.setattr(pi_mod, "_run_agent", run_agent_spy)

        wt_path = tmp_path / "worktree"
        pi_mod.invoke_agent_with_output("prompt", 1, worktree_path=wt_path)

        assert run_agent_spy.call_count == 1
        _, kwargs = run_agent_spy.call_args
        assert kwargs.get("worktree_path") == wt_path

    def test_default_cwd_is_project_root(self, monkeypatch) -> None:
        """Without a worktree path, _run_agent uses cwd=PROJECT_ROOT."""
        from core.pipeline.agents import pi as pi_mod

        monkeypatch.setattr(pi_mod, "_resolve_agent_binary", lambda: "pi")
        run_agent_spy = mock.Mock(
            return_value=mock.Mock(returncode=0, stdout=b"", stderr=b"")
        )
        monkeypatch.setattr(pi_mod, "_run_agent", run_agent_spy)

        pi_mod.invoke_agent_with_output("prompt", 1)

        _, kwargs = run_agent_spy.call_args
        assert kwargs.get("worktree_path") is None
