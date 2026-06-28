"""Kimi agent wrapper (C1 step 9 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the kimi agent wrapper
lives at ``core/pipeline/agents/kimi.py``. It delegates to the
shared invocation path in ``core.pipeline.agents.pi``.

Per spec §10.1 A3 (R1): kimi and pi use the same invocation path
(no kimi-specific ``--continue`` workaround). The only difference
is the non-interactive flag (``--prompt`` for kimi vs ``--print``
for pi); both are handled inside ``invoke_agent``.
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

from core.pipeline.agents.base import AgentBase  # noqa: E402
from core.pipeline.agents.pi import invoke_agent  # noqa: E402


class KimiAgent(AgentBase):
    """Wrapper for the ``kimi`` agent binary.

    Per spec §10.1 A3: symmetric with :class:`PiAgent` — NO
    ``--continue`` / ``--session`` flags. The kimi-specific
    session-UUID workaround was removed in A3.3 (plan §3 R-1).
    """

    name = "kimi"

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to :func:`invoke_agent`."""
        return invoke_agent(*args, **kwargs)


__all__ = ["KimiAgent"]
