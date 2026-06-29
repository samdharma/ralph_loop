"""Checkpoint save/clear (C1 step 2 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, checkpoint helpers live at
``core/pipeline/checkpoint.py``. They write ``.ralph/checkpoint.json``
on stage start so a daemon SIGKILL can be detected on next startup
and the working tree rolled back to the pre-stage SHA.

The companion Pydantic model ``CheckpointState`` (per spec §6.1)
lives in ``core/schemas/checkpoint.py``.

The crash-recovery logic itself (``recover_from_crash``) lives in
``core/pipeline/recovery.py`` and is re-exported here via a
``__getattr__`` lazy import so existing callers that
``from core.pipeline.checkpoint import recover_from_crash`` keep
working unchanged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap sys.path so ``from core.pipeline...`` and the
# engine module can be resolved when this file is loaded via pytest
# from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# PROJECT_ROOT is the directory containing ``.ralph/``. Tests override
# this via ``monkeypatch.setattr`` (e.g., ``monkeypatch.setattr(
# checkpoint, "PROJECT_ROOT", tmp_path)``).
PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
CHECKPOINT_FILE = PROJECT_ROOT / ".ralph" / "checkpoint.json"


def _run_git(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke ``git`` with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["git", *argv],
        capture_output=True,
        check=False,
        cwd=PROJECT_ROOT,
    )


def save_checkpoint(issue_num: int, stage: str):
    """Save checkpoint for crash recovery with stage info.

    Writes ``.ralph/checkpoint.json`` containing the issue number,
    current stage, pre-stage HEAD SHA, and an ISO timestamp. The
    SHA is captured at write time so a future crash recovery can
    roll back the working tree to the pre-stage state via
    ``git reset --hard <pre_sha>``.
    """
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    pre_sha = (
        _run_git(["rev-parse", "HEAD"]).stdout.strip().decode("utf-8", errors="replace")
    )
    data = {
        "issue": issue_num,
        "stage": stage,
        "pre_stage_sha": pre_sha,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2))


def clear_checkpoint():
    """Remove checkpoint file on clean completion."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


# ``recover_from_crash`` is owned by ``core/pipeline/recovery.py``
# (C1 step 3). It is re-exported from this module so existing callers
# that ``from core.pipeline.checkpoint import recover_from_crash``
# keep working unchanged. To avoid a circular import at module-load
# time (engine.py imports save_checkpoint/clear_checkpoint from this
# module; if we eagerly imported recover_from_crash from engine.py
# we'd loop), we do the import lazily in ``__getattr__``.
_recover_from_crash = None


def __getattr__(name: str):  # noqa: D401
    """PEP 562 lazy attribute lookup for backward-compat re-exports."""
    global _recover_from_crash
    if name == "recover_from_crash":
        if _recover_from_crash is None:
            from core.pipeline.recovery import recover_from_crash as _impl

            _recover_from_crash = _impl
        return _recover_from_crash
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "save_checkpoint",
    "clear_checkpoint",
    "PROJECT_ROOT",
    "CHECKPOINT_FILE",
]  # noqa: D401
