"""Pytest conftest at repo root.

Resolves the ``core`` package import so test files (especially
those under tests/unit/core/pipeline/...) can do
``from core.engine import ...`` and ``import project_sync``
without each test file needing its own sys.path bootstrap.

The project layout has ``core/`` as a directory containing both
the ``core`` package (subpackages like ``pipeline/``) and flat
modules (``engine.py``, ``validate.py``, ``project_sync.py``).
For pytest test discovery, we need:
  - Repo root on sys.path so ``core`` is a package import.
  - ``core/`` directory on sys.path so flat modules like
    ``project_sync`` are importable.

This conftest sets both up before any test module is imported.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CORE_DIR = REPO_ROOT / "core"

# Add repo root first (so ``from core.X import Y`` works),
# then ``core/`` directory (so flat modules like ``project_sync``
# are importable as top-level modules).
for p in (str(REPO_ROOT), str(CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)