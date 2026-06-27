"""Tests for TrajectoryEvent discriminated union.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §4.2 and §10.2 B4.

TrajectoryEvent is a Pydantic v2 union type with the discriminator field
``event_type``. Each variant has its own typed payload. The variant set
covers the engine's observable actions across all stages:

    - StageTransition
    - SubagentInvocation
    - ValidationRun
    - LabelTransition
    - Retry

These tests verify:
    1. Every variant serializes with its ``event_type`` discriminator.
    2. ``TrajectoryEvent.model_validate(json_dict)`` reconstructs the
       correct variant from its JSON form (round-trip).
    3. An invalid ``event_type`` raises ``ValidationError``.

Per spec §4.2 the model is read-only at first — no validation logic
beyond type checking. We focus on shape and discriminator fidelity.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

# Import path that the GREEN task will create:
from core.schemas.events import TrajectoryEvent


# ---------------------------------------------------------------------------
# Shared fixtures: timestamps for deterministic test data.
# ---------------------------------------------------------------------------

T0 = datetime(2026, 6, 27, 15, 30, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 6, 27, 15, 35, 12, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# StageTransition — emitted when the engine advances an issue from one
# status:* label to another.
# ---------------------------------------------------------------------------


def test_stage_transition_serializes_with_event_type() -> None:
    """StageTransition carries `event_type=stage_transition` in JSON form."""
    evt = TrajectoryEvent(
        **{
            "event_type": "stage_transition",
            "timestamp": T0,
            "issue_num": 42,
            "from_stage": "ready",
            "to_stage": "design",
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )
    payload = evt.model_dump(mode="json")
    assert payload["event_type"] == "stage_transition"
    assert payload["issue_num"] == 42
    assert payload["from_stage"] == "ready"
    assert payload["to_stage"] == "design"


# ---------------------------------------------------------------------------
# SubagentInvocation — emitted when an AI sub-agent (pi/kimi) is invoked.
# ---------------------------------------------------------------------------


def test_subagent_invocation_serializes_with_event_type() -> None:
    """SubagentInvocation records the agent binary and prompt size."""
    evt = TrajectoryEvent(
        **{
            "event_type": "subagent_invocation",
            "timestamp": T0,
            "issue_num": 42,
            "agent_binary": "pi",
            "prompt_size_bytes": 12345,
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )
    payload = evt.model_dump(mode="json")
    assert payload["event_type"] == "subagent_invocation"
    assert payload["agent_binary"] == "pi"
    assert payload["prompt_size_bytes"] == 12345


# ---------------------------------------------------------------------------
# ValidationRun — emitted when `run_pytest_invocation` executes.
# ---------------------------------------------------------------------------


def test_validation_run_serializes_with_event_type() -> None:
    """ValidationRun records the structured pytest result."""
    evt = TrajectoryEvent(
        **{
            "event_type": "validation_run",
            "timestamp": T1,
            "issue_num": 42,
            "exit_code": 0,
            "classification": "success",
            "action": "accept",
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )
    payload = evt.model_dump(mode="json")
    assert payload["event_type"] == "validation_run"
    assert payload["exit_code"] == 0
    assert payload["classification"] == "success"
    assert payload["action"] == "accept"


# ---------------------------------------------------------------------------
# LabelTransition — emitted when `gh issue edit --add-label/--remove-label`
# is invoked.
# ---------------------------------------------------------------------------


def test_label_transition_serializes_with_event_type() -> None:
    """LabelTransition records add/remove label lists."""
    evt = TrajectoryEvent(
        **{
            "event_type": "label_transition",
            "timestamp": T0,
            "issue_num": 42,
            "added": ["status:design"],
            "removed": ["status:ready"],
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )
    payload = evt.model_dump(mode="json")
    assert payload["event_type"] == "label_transition"
    assert payload["added"] == ["status:design"]
    assert payload["removed"] == ["status:ready"]


# ---------------------------------------------------------------------------
# Retry — emitted when the engine retries an action.
# ---------------------------------------------------------------------------


def test_retry_serializes_with_event_type() -> None:
    """Retry records attempt number and the previous action's classification."""
    evt = TrajectoryEvent(
        **{
            "event_type": "retry",
            "timestamp": T1,
            "issue_num": 42,
            "attempt": 2,
            "previous_classification": "timeout",
            "previous_action": "retry_transient",
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )
    payload = evt.model_dump(mode="json")
    assert payload["event_type"] == "retry"
    assert payload["attempt"] == 2
    assert payload["previous_classification"] == "timeout"


# ---------------------------------------------------------------------------
# Round-trip and discriminator fidelity.
# ---------------------------------------------------------------------------


def test_model_validate_round_trip_reconstructs_variant() -> None:
    """Serialize → JSON → deserialize → same variant."""
    original = TrajectoryEvent(
        **{
            "event_type": "stage_transition",
            "timestamp": T0,
            "issue_num": 42,
            "from_stage": "ready",
            "to_stage": "design",
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )
    as_json = original.model_dump(mode="json")
    raw = json.loads(json.dumps(as_json))
    reconstructed = TrajectoryEvent.model_validate(raw)
    assert type(reconstructed) is type(original)
    assert reconstructed.event_type == original.event_type
    assert reconstructed.model_dump(mode="json") == as_json


def test_invalid_event_type_raises_validation_error() -> None:
    """Unknown event_type discriminator → ValidationError."""
    with pytest.raises(ValidationError):
        TrajectoryEvent(
            **{
                "event_type": "this_variant_does_not_exist",
                "timestamp": T0,
                "issue_num": 42,
                "run_id": "20260627T1530-a1b2c3d4",
            }
        )


def test_event_type_discriminator_is_set_on_instance() -> None:
    """All constructed instances expose a string event_type attribute."""
    evt = TrajectoryEvent(
        **{
            "event_type": "retry",
            "timestamp": T1,
            "issue_num": 42,
            "attempt": 1,
            "previous_classification": "test_failure",
            "previous_action": "retry_l2",
            "run_id": "20260627T1530-a1b2c3d4",
        }
    )
    assert isinstance(evt.event_type, str)
    assert evt.event_type == "retry"