"""Trajectory event schemas.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §4.2 (Pydantic models) and §10.2 B4
(Single trajectory file).

The :class:`TrajectoryEvent` type is a Pydantic v2 discriminated union over
``event_type``. Every engine side effect that affects an issue's progress
emits exactly one of these events to ``.ralph/issues/<N>/trajectory.jsonl``.

This module is intentionally read-only at the type level — it defines the
shape of an event, not where or how it is written. The writer lives in
:mod:`core.pipeline.metrics`.

Variants:

- :class:`StageTransition` — engine advanced an issue from one status:* to another.
- :class:`SubagentInvocation` — an AI sub-agent (pi or kimi) was invoked.
- :class:`ValidationRun` — a ``run_pytest_invocation`` cycle completed.
- :class:`LabelTransition` — ``gh issue edit --add/--remove-label`` was issued.
- :class:`Retry` — the engine retried a previously-failed action.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel


class _BaseEvent(BaseModel):
    """Shared fields for every trajectory event variant.

    All variants carry these fields so downstream consumers can index
    by ``issue_num`` and ``timestamp`` without per-variant handling.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: datetime
    issue_num: int
    run_id: str


class StageTransition(_BaseEvent):
    """Engine advanced an issue from one ``status:*`` label to another."""

    event_type: Literal["stage_transition"]
    from_stage: str
    to_stage: str


class SubagentInvocation(_BaseEvent):
    """An AI sub-agent (pi or kimi) was invoked for this issue."""

    event_type: Literal["subagent_invocation"]
    agent_binary: str
    prompt_size_bytes: int


class ValidationRun(_BaseEvent):
    """A ``run_pytest_invocation`` cycle completed (success or failure)."""

    event_type: Literal["validation_run"]
    exit_code: int
    classification: str
    action: str


class LabelTransition(_BaseEvent):
    """``gh issue edit --add/--remove-label`` was issued."""

    event_type: Literal["label_transition"]
    added: list[str]
    removed: list[str]


class Retry(_BaseEvent):
    """The engine retried a previously-failed action."""

    event_type: Literal["retry"]
    attempt: int
    previous_classification: str
    previous_action: str


# Discriminated union — Pydantic v2 picks the right variant by the
# ``event_type`` field. ``RootModel`` wraps it so callers can use
# ``TrajectoryEvent(**payload)`` and ``TrajectoryEvent.model_validate(...)``
# directly.
_TrajectoryEventUnion = Annotated[
    Union[
        StageTransition,
        SubagentInvocation,
        ValidationRun,
        LabelTransition,
        Retry,
    ],
    Field(discriminator="event_type"),
]


class TrajectoryEvent(RootModel[_TrajectoryEventUnion]):
    """A single trajectory event.

    Wraps the discriminated union as a Pydantic v2 ``RootModel`` so
    callers can use ``TrajectoryEvent(...)`` as a constructor and
    ``TrajectoryEvent.model_validate(...)`` to parse JSON.
    """

    root: _TrajectoryEventUnion

    # Forward discriminator access to the wrapped instance so users
    # can read ``evt.event_type`` without first unpacking ``.root``.
    @property
    def event_type(self) -> str:
        return self.root.event_type

    def __getattr__(self, name: str) -> object:
        # Delegate attribute reads that aren't on RootModel itself
        # to the wrapped event so callers can write
        # ``evt.timestamp`` rather than ``evt.root.timestamp``.
        return getattr(self.root, name)


__all__ = [
    "TrajectoryEvent",
    "StageTransition",
    "SubagentInvocation",
    "ValidationRun",
    "LabelTransition",
    "Retry",
]
