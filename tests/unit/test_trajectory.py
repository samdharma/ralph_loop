"""Tests for ralph trajectory <N> command.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §5.2 and §10.2 B4.

``core.trajectory.print_trajectory(issue_num)`` reads
``.ralph/issues/<N>/trajectory.jsonl`` and prints a human-readable
timeline. The output format is one line per event::

    2026-06-27T15:30:01  StageTransition       ready → design

Tests verify:
  1. ``print_trajectory`` outputs each event's ``event_type`` and timestamp.
  2. Output preserves the file's event order.
  3. Missing ``trajectory.jsonl`` produces a clear error message
     and a non-zero exit status.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

from core import trajectory as trajectory_mod  # noqa: E402
from core.pipeline import metrics  # noqa: E402
from core.schemas.events import TrajectoryEvent  # noqa: E402


def _stage_transition(issue_num: int, ts: datetime, from_s: str, to_s: str) -> TrajectoryEvent:
    return TrajectoryEvent.model_validate(
        {
            "event_type": "stage_transition",
            "timestamp": ts,
            "issue_num": issue_num,
            "from_stage": from_s,
            "to_stage": to_s,
            "run_id": "20260627T1530-aaaa",
        }
    )


def test_print_trajectory_outputs_event_types_and_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """print_trajectory outputs each event's event_type and timestamp."""
    monkeypatch.setattr(metrics, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(trajectory_mod, "PROJECT_ROOT", tmp_path)

    ts1 = datetime(2026, 6, 27, 15, 30, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 6, 27, 15, 35, 12, tzinfo=timezone.utc)

    metrics.append_trajectory_event(1, _stage_transition(1, ts1, "ready", "design"))
    metrics.append_trajectory_event(1, _stage_transition(1, ts2, "design", "build"))

    buf = io.StringIO()
    with redirect_stdout(buf):
        trajectory_mod.print_trajectory(1)

    out = buf.getvalue()
    assert "stage_transition" in out
    assert "2026-06-27T15:30" in out or "15:30" in out


def test_print_trajectory_preserves_event_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Output preserves the order of events in the file."""
    monkeypatch.setattr(metrics, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(trajectory_mod, "PROJECT_ROOT", tmp_path)

    ts1 = datetime(2026, 6, 27, 15, 30, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 6, 27, 15, 35, 0, tzinfo=timezone.utc)
    ts3 = datetime(2026, 6, 27, 15, 40, 0, tzinfo=timezone.utc)

    metrics.append_trajectory_event(1, _stage_transition(1, ts1, "ready", "design"))
    metrics.append_trajectory_event(
        1,
        TrajectoryEvent.model_validate(
            {
                "event_type": "validation_run",
                "timestamp": ts2,
                "issue_num": 1,
                "exit_code": 0,
                "classification": "success",
                "action": "accept",
                "run_id": "20260627T1530-aaaa",
            }
        ),
    )
    metrics.append_trajectory_event(
        1,
        TrajectoryEvent.model_validate(
            {
                "event_type": "label_transition",
                "timestamp": ts3,
                "issue_num": 1,
                "added": ["status:build"],
                "removed": ["status:design"],
                "run_id": "20260627T1530-aaaa",
            }
        ),
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        trajectory_mod.print_trajectory(1)

    out = buf.getvalue()
    pos_design = out.find("stage_transition")
    pos_val = out.find("validation_run")
    pos_label = out.find("label_transition")
    assert pos_design < pos_val < pos_label


def test_print_trajectory_missing_file_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing trajectory.jsonl → non-zero exit + clear error message."""
    monkeypatch.setattr(metrics, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(trajectory_mod, "PROJECT_ROOT", tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        trajectory_mod.print_trajectory(999)

    assert exc_info.value.code != 0


def test_print_trajectory_missing_file_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing trajectory.jsonl produces a clear error message on stderr."""
    monkeypatch.setattr(metrics, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(trajectory_mod, "PROJECT_ROOT", tmp_path)

    with pytest.raises(SystemExit):
        trajectory_mod.print_trajectory(999)

    captured = capsys.readouterr()
    assert "999" in captured.err or "999" in captured.out