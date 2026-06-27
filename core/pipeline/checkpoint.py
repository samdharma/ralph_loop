"""Checkpoint save/clear/recover (C1.7a — per plan §1.1 C1.7).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, checkpoint helpers live at
``core/pipeline/checkpoint.py``. DEVIATION: thin wrapper that
delegates to engine.save_checkpoint / clear_checkpoint /
recover_from_crash; the actual implementations stay in engine.py
pending C-046.

The companion Pydantic model ``CheckpointState`` (per spec §6.1)
lives in core/schemas/checkpoint.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.engine import (  # noqa: E402,F401
    clear_checkpoint,
    recover_from_crash,
    save_checkpoint,
)

__all__ = ["save_checkpoint", "clear_checkpoint", "recover_from_crash"]
