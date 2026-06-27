"""GitHub Project/Kanban board sync helper (C1.6d — per plan §1.1 C1.6).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, sync_status / sync_closed
live at ``core/pipeline/github/board.py``. DEVIATION: thin wrapper.
"""

from __future__ import annotations

# Use the package-style import so this module is findable by mypy
# (mypy --strict treats ``from project_sync import`` as flat-module
# import which only works when core/ is on sys.path).
from core.project_sync import sync_closed, sync_status  # noqa: F401

__all__ = ["sync_status", "sync_closed"]
