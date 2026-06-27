"""Pi agent wrapper (C1.5b — per plan §1.1 C1.5).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the pi agent wrapper lives
at ``core/pipeline/agents/pi.py``. DEVIATION: thin wrapper that
delegates to engine.invoke_agent; the actual implementation stays
in engine.py pending C-046.
"""

from __future__ import annotations

import sys
from abc import abstractmethod
from pathlib import Path
from typing import Any

# Bootstrap sys.path (covered by conftest.py in pytest context, but
# included here for direct-import robustness).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.engine import invoke_agent as _engine_invoke_agent  # noqa: E402
from core.pipeline.agents.base import AgentBase  # noqa: E402


class PiAgent(AgentBase):
    """Wrapper for the ``pi`` agent binary.

    Per spec §10.1 A3: NO --continue / --session flags. The
    implementation in engine.invoke_agent handles this constraint.
    """

    name = "pi"

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to engine.invoke_agent with binary='pi'."""
        kwargs.setdefault("binary", "pi")
        return _engine_invoke_agent(*args, **kwargs)


__all__ = ["PiAgent"]
