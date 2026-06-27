"""Tests for core.pipeline.runner module (C1.3).

Per docs/IMPROVEMENT_ROADMAP_PLAN.md §1.1 C1.3 and §3 R-2:

``core/pipeline/runner.py`` exposes the top-level pipeline loop and
the per-issue pipeline runner. These were originally in
``core/engine.py:536-727, 2387-2618`` and are moved here as part of
the C1 refactor.

These tests pin the public API at the new path. They re-import from
``core.pipeline.runner`` and assert that the function signatures and
docstrings are preserved.
"""

from __future__ import annotations

import inspect

import pytest


class TestRunnerAtNewPath:
    """C1.3: runner module is at core/pipeline/runner.py."""

    def test_run_loop_importable_from_runner(self) -> None:
        """``from core.pipeline.runner import run_loop`` succeeds."""
        from core.pipeline.runner import run_loop

        assert callable(run_loop)

    def test_run_pipeline_importable_from_runner(self) -> None:
        """``from core.pipeline.runner import run_pipeline`` succeeds."""
        from core.pipeline.runner import run_pipeline

        assert callable(run_pipeline)

    def test_run_loop_has_docstring(self) -> None:
        """run_loop preserves its docstring (parity with original)."""
        from core.pipeline.runner import run_loop

        assert run_loop.__doc__, "run_loop must have a docstring"
        # Should mention it's the main loop.
        assert "loop" in run_loop.__doc__.lower()

    def test_run_pipeline_has_docstring(self) -> None:
        """run_pipeline preserves its docstring (parity with original)."""
        from core.pipeline.runner import run_pipeline

        assert run_pipeline.__doc__, "run_pipeline must have a docstring"
        # Should mention pipeline / stage.
        assert "pipeline" in run_pipeline.__doc__.lower()

    def test_run_loop_signature_preserved(self) -> None:
        """run_loop accepts the same arguments as the original."""
        from core.pipeline.runner import run_loop

        sig = inspect.signature(run_loop)
        # Original signature: (auto_close=False, single_issue=None)
        params = sig.parameters
        assert "auto_close" in params
        assert "single_issue" in params

    def test_run_pipeline_signature_preserved(self) -> None:
        """run_pipeline accepts the same arguments as the original."""
        from core.pipeline.runner import run_pipeline

        sig = inspect.signature(run_pipeline)
        params = sig.parameters
        assert "issue" in params
        assert "auto_close" in params
        assert "resume_stage" in params


@pytest.fixture
def cleanup_state():
    """No-op fixture placeholder; runner tests don't share state."""
    yield
