"""Label-transition helper (C1.6b — per plan §1.1 C1.6).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, transition_label lives at
``core/pipeline/github/labels.py``. DEVIATION: thin wrapper that
delegates to engine.transition_label; the actual implementation
stays in engine.py pending C-046.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap sys.path (covered by conftest.py in pytest context).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.engine import transition_label  # noqa: E402,F401

__all__ = ["transition_label"]
