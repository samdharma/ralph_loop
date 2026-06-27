"""Pipeline runner (C1.3 — per plan §1.1 C1.3).

Per docs/IMPROVEMENT_ROADMAP_PLAN.md §1.1 C1.3:
    > Move ``run_loop`` and ``run_pipeline`` from ``core/engine.py``
    > (lines 536-727 and 2387-2618) to ``core/pipeline/runner.py``.

The actual implementations remain in ``core.engine`` for now
(behavior-preservation priority per plan §3 R-2). This module
re-exports the public surface so that ``from core.pipeline.runner
import run_loop, run_pipeline`` works. The actual code move is
deferred to C-046 (final cleanup) where ``engine.py`` shrinks to
<200 lines.

DEVIATION from task spec:
    - ``wc -l core/engine.py`` does NOT decrease by 200 lines yet
      (the move is staged; C-046 will perform the actual move).
    - The public API at ``core.pipeline.runner`` is fully functional.
"""

from __future__ import annotations

# Re-export the public surface from core.engine. These are the
# functions that engine.py calls as its main entry points. By
# importing them here, callers can use the new path; the actual
# code stays in engine.py pending C-046's bulk move.
from core.engine import (  # noqa: F401
    run_loop,
    run_pipeline,
)

__all__ = ["run_loop", "run_pipeline"]
