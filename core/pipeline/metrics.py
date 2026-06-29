"""Trajectory writer.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.2 and §10.2 B4.

The trajectory is the single source of truth for "what happened to
this issue". It lives at ``.ralph/issues/<N>/trajectory.jsonl`` and
holds one JSON object per line (JSONL format).

This module exposes two functions:

  - :func:`append_trajectory_event` — write one event to the JSONL file,
    creating parent directories as needed.
  - :func:`read_trajectory` — parse the file back into a list of
    :class:`TrajectoryEvent` instances.

Path resolution:

  The on-disk path is ``PROJECT_ROOT / '.ralph' / 'issues' / <N>
  / 'trajectory.jsonl'``. ``PROJECT_ROOT`` defaults to :data:`PROJECT_ROOT`
  (the current working directory) but is overridable for tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.schemas.events import TrajectoryEvent

# PROJECT_ROOT is the directory containing ``.ralph/``. Tests override
# this via ``monkeypatch.setattr(metrics, "PROJECT_ROOT", tmp_path)``.
PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


def _trajectory_path(issue_num: int) -> Path:
    """Return the on-disk path for issue ``issue_num``'s trajectory."""
    return PROJECT_ROOT / ".ralph" / "issues" / str(issue_num) / "trajectory.jsonl"


def append_trajectory_event(issue_num: int, event: TrajectoryEvent) -> None:
    """Append one event to ``.ralph/issues/<N>/trajectory.jsonl``.

    The parent directory is created on first append. Each event is
    serialized as a single JSON object on its own line (JSONL).
    """
    path = _trajectory_path(issue_num)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = event.model_dump(mode="json")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload))
        f.write("\n")


def read_trajectory(issue_num: int) -> list[TrajectoryEvent]:
    """Read all events from ``.ralph/issues/<N>/trajectory.jsonl``.

    Returns an empty list if the file does not exist. Each line is
    parsed back into a :class:`TrajectoryEvent` via ``model_validate``.
    """
    path = _trajectory_path(issue_num)
    if not path.exists():
        return []
    events: list[TrajectoryEvent] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(raw_line)
        events.append(TrajectoryEvent.model_validate(raw))
    return events
