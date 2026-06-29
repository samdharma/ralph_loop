"""Shell helpers and canonical project-path constants.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, low-level subprocess wrappers
and the canonical PROJECT_ROOT / LOG_DIR / METRICS_FILE / PROMPT_FILE /
PROMPTS_DIR / DESIGN_SPEC_DIR / PREFLIGHT_SCRIPT constants live here so
that other pipeline modules can depend on them without importing
``core.engine``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Bootstrap sys.path so ``from core.pipeline...`` and the
# engine module can be resolved when this file is loaded via pytest
# from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# PROJECT_ROOT is the directory containing ``.ralph/``. Tests override
# this via ``monkeypatch.setattr``.
PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
LOG_DIR = PROJECT_ROOT / "logs"
METRICS_FILE = LOG_DIR / "ralph_metrics.jsonl"
PROMPT_FILE = PROJECT_ROOT / "docs" / "agent" / "PROMPT.md"
PROMPTS_DIR = PROJECT_ROOT / "docs" / "agent" / "prompts"

# Per-issue design specs live in docs/designs/<N>.md (one file per issue).
DESIGN_SPEC_DIR = PROJECT_ROOT / "docs" / "designs"
PREFLIGHT_SCRIPT = PROJECT_ROOT / "config" / "ralph_preflight.sh"

# Backoff used when all available agents are rate-limited.
RATE_LIMIT_BACKOFF_SECONDS = 15 * 60  # 15 minutes


def run(
    cmd: list[str],
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run a shell command, return CompletedProcess."""
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
        timeout=timeout,
        cwd=PROJECT_ROOT,
    )
    # Lazy import avoids any module-load ordering concerns with recovery.py.
    from core.pipeline.recovery import _check_interrupt

    _check_interrupt()
    return result


def gh(*args: str) -> subprocess.CompletedProcess:
    """Run `gh` command. Raises on failure."""
    return run(["gh", *args])


def git(*args: str) -> subprocess.CompletedProcess:
    """Run `git` command. Raises on failure."""
    return run(["git", *args])


__all__ = [
    "PROJECT_ROOT",
    "LOG_DIR",
    "METRICS_FILE",
    "PROMPT_FILE",
    "PROMPTS_DIR",
    "DESIGN_SPEC_DIR",
    "PREFLIGHT_SCRIPT",
    "RATE_LIMIT_BACKOFF_SECONDS",
    "run",
    "gh",
    "git",
]
