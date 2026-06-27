"""Tests for the trajectory writer.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §10.2 B4 and §6.2.

``core.pipeline.metrics`` exposes two functions:
  - append_trajectory_event(issue_num, event) → writes one JSONL line.
  - read_trajectory(issue_num) → returns the list of events.

The on-disk path is ``.ralph/issues/<N>/trajectory.jsonl``. The parent
directory is created on first append.

Tests verify:
  1. First append creates the file with one JSON line.
  2. Two appends produce a file with exactly two JSON lines.
  3. ``read_trajectory`` returns the appended events in order.
  4. Every line is valid JSON parseable by ``json.loads``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "core"))

from core.pipeline import metrics  # noqa: E402
from core.schemas.events import (  # noqa: E402
    TrajectoryEvent,
)

T0 = datetime(2026, 6, 27, 15, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PROJECT_ROOT at tmp_path so trajectory files land under tmp_path/.ralph/."""
    monkeypatch.setattr(metrics, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _stage_transition(issue_num: int) -> TrajectoryEvent:
    return TrajectoryEvent.model_validate(
        {
            "event_type": "stage_transition",
            "timestamp": T0,
            "issue_num": issue_num,
            "from_stage": "ready",
            "to_stage": "design",
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )


def test_append_creates_file_with_one_json_line(
    project_root: Path,
) -> None:
    """The first append creates the directory and writes one JSONL line."""
    metrics.append_trajectory_event(1, _stage_transition(1))

    trajectory_file = project_root / ".ralph" / "issues" / "1" / "trajectory.jsonl"
    assert trajectory_file.exists()
    lines = trajectory_file.read_text().splitlines()
    assert len(lines) == 1


def test_two_appends_produce_two_lines(project_root: Path) -> None:
    """Each append writes exactly one line; two appends ⇒ two lines."""
    metrics.append_trajectory_event(1, _stage_transition(1))
    metrics.append_trajectory_event(
        1,
        TrajectoryEvent.model_validate(
            {
                "event_type": "validation_run",
                "timestamp": T0,
                "issue_num": 1,
                "exit_code": 0,
                "classification": "success",
                "action": "accept",
                "run_id": "20260627T1530-a1b2c3d4",
            }
        ),
    )

    trajectory_file = project_root / ".ralph" / "issues" / "1" / "trajectory.jsonl"
    lines = trajectory_file.read_text().splitlines()
    assert len(lines) == 2


def test_read_trajectory_returns_appended_events_in_order(
    project_root: Path,
) -> None:
    """read_trajectory returns events in append order."""
    evt_a = _stage_transition(1)
    evt_b = TrajectoryEvent.model_validate(
        {
            "event_type": "retry",
            "timestamp": T0,
            "issue_num": 1,
            "attempt": 1,
            "previous_classification": "test_failure",
            "previous_action": "retry_l2",
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )

    metrics.append_trajectory_event(1, evt_a)
    metrics.append_trajectory_event(1, evt_b)

    events = metrics.read_trajectory(1)
    assert len(events) == 2
    assert events[0].event_type == "stage_transition"
    assert events[1].event_type == "retry"


def test_each_line_is_valid_json(project_root: Path) -> None:
    """Every appended line is parseable by ``json.loads``."""
    metrics.append_trajectory_event(1, _stage_transition(1))
    metrics.append_trajectory_event(1, _stage_transition(1))

    trajectory_file = project_root / ".ralph" / "issues" / "1" / "trajectory.jsonl"
    for line in trajectory_file.read_text().splitlines():
        payload = json.loads(line)
        assert "event_type" in payload
        assert "issue_num" in payload
