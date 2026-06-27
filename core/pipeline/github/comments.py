"""Comment helper (C1.6c — per plan §1.1 C1.6).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, gh_comment lives at
``core/pipeline/github/comments.py``. DEVIATION: thin wrapper.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.engine import gh_comment  # noqa: E402,F401

__all__ = ["gh_comment"]
