"""Kimi agent wrapper (C1.5c — per plan §1.1 C1.5).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the kimi agent wrapper lives
at ``core/pipeline/agents/kimi.py``. DEVIATION: thin wrapper that
delegates to engine.invoke_agent; the actual implementation stays
in engine.py pending C-046.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Bootstrap sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.engine import invoke_agent as _engine_invoke_agent  # noqa: E402
from core.pipeline.agents.base import AgentBase  # noqa: E402


class KimiAgent(AgentBase):
    """Wrapper for the ``kimi`` agent binary.

    Per spec §10.1 A3: symmetric with PiAgent — NO --continue /
    --session flags. The kimi-specific session-UUID workaround was
    removed in A3.3.
    """

    name = "kimi"

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to engine.invoke_agent with binary='kimi'."""
        kwargs.setdefault("binary", "kimi")
        return _engine_invoke_agent(*args, **kwargs)


__all__ = ["KimiAgent"]
