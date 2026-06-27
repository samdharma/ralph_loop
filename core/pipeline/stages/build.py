"""BUILD stage (C1.4b — per plan §1.1 C1.4).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the BUILD stage lives at
``core/pipeline/stages/build.py``.

DEVIATION: similar to DesignStage — class wraps engine.run_build_stage.
The original function stays in engine.py pending C-046.
"""

from __future__ import annotations

from typing import Any

from core.engine import run_build_stage as _engine_run_build_stage
from core.pipeline.stages.base import Stage


class BuildStage(Stage):
    """BUILD pipeline stage — runs TEST + IMPLEMENT sub-agents."""

    name = "build"

    def run(self, issue: dict, **kwargs: Any) -> bool:
        """Run the BUILD stage. Delegates to engine.run_build_stage."""
        return _engine_run_build_stage(issue)


__all__ = ["BuildStage"]
