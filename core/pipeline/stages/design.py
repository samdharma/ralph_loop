"""DESIGN stage (C1.4a — per plan §1.1 C1.4).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the DESIGN stage lives at
``core/pipeline/stages/design.py``.

DEVIATION from task spec:
    The task assumes DesignStage is a class that inherits from Stage.
    The original ``run_design_stage`` is a top-level function in
    engine.py. We expose DesignStage as a thin class that wraps the
    original function via Stage's ABC. The original function stays
    in engine.py pending C-046's bulk move.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Bootstrap sys.path so core.engine and core.pipeline.stages.base can
# be imported when this module is loaded via pytest from a tests/
# subdirectory. Both the project root (for the core package) and the
# core/ directory (for flat modules like project_sync) must be present.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.engine import run_design_stage as _engine_run_design_stage  # noqa: E402
from core.pipeline.stages.base import Stage  # noqa: E402


class DesignStage(Stage):
    """DESIGN pipeline stage — runs the architect sub-agent."""

    name = "design"

    def run(self, issue: dict, **kwargs: Any) -> bool:
        """Run the DESIGN stage. Delegates to engine.run_design_stage."""
        return _engine_run_design_stage(issue)


__all__ = ["DesignStage"]
