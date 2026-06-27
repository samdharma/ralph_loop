"""VERIFY stage (C1.4c — per plan §1.1 C1.4).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the VERIFY stage lives at
``core/pipeline/stages/verify.py``.

DEVIATION: similar to DesignStage — class wraps engine.run_verify_stage.
"""

from __future__ import annotations

from typing import Any

from core.engine import run_verify_stage as _engine_run_verify_stage
from core.pipeline.stages.base import Stage


class VerifyStage(Stage):
    """VERIFY pipeline stage — runs the reviewer sub-agent."""

    name = "verify"

    def run(self, issue: dict, **kwargs: Any) -> bool:
        """Run the VERIFY stage. Delegates to engine.run_verify_stage."""
        return _engine_run_verify_stage(issue)


__all__ = ["VerifyStage"]
