"""Pipeline state: run_id generator and Stage enum.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §4.2, §7.2, and §10.2 B2.

This module is the smallest unit of "typed pipeline state" introduced
in Phase B. It exposes:

  - :class:`Stage` — the eight-state label machine as a ``str`` enum.
  - :data:`STATUS_LABEL` — mapping from :class:`Stage` to its
    ``status:<value>`` label string.
  - :func:`generate_run_id` — a unique run identifier used to key
    idempotency records and trajectory events.

Per spec §7.2: enums replace string literals for stages; status labels
are derived from the enum rather than hand-written throughout the
codebase. Per spec §10.2 B2: run_id is the discriminator that prevents
double-execution of engine side effects across crash/restart cycles.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Stage(str, Enum):
    """The eight-state label machine used by Ralph's pipeline.

    Per spec §9.1.5 no new ``status:*`` labels may be added in v3.1.x —
    the existing six labels above are the closed set. D2 introduces
    ``status:retry`` as the single allowed addition.

    ``str`` mixin lets the enum serialize as its string value when
    used in JSON payloads or label comparisons.
    """

    READY = "ready"
    DESIGN = "design"
    BUILD = "build"
    VERIFY = "verify"
    REVIEW = "review"
    BLOCKED = "blocked"


# STATUS_LABEL is the canonical mapping from a Stage value to its
# ``status:<value>`` label string used in ``gh issue edit`` calls.
STATUS_LABEL: dict[Stage, str] = {s: f"status:{s.value}" for s in Stage}


class PipelineState(BaseModel):
    """Typed per-issue pipeline state (per spec §6.1, §7.2).

    Holds the minimal fields needed to resume a pipeline across
    crash/restart cycles. ``stage`` is the current stage; ``pre_sha``
    is the commit hash at which the issue was claimed (for rollback);
    ``run_id`` is the per-run idempotency discriminator (per spec
    §10.2 B2).

    Pydantic v2 model per spec §4.2 — validates inputs at the boundary
    so downstream code can rely on typed fields.
    """

    model_config = ConfigDict(frozen=False, use_enum_values=False)

    issue_num: int = Field(..., description="GitHub issue number")
    stage: Stage = Field(..., description="Current pipeline stage")
    pre_sha: str = Field(
        default="",
        description="Commit SHA at which the issue was claimed (for rollback)",
    )
    run_id: str = Field(
        default="",
        description="Unique run identifier for this pipeline run (idempotency key)",
    )


def generate_run_id() -> str:
    """Return a unique run identifier of the form ``<timestamp>-<uuid8>``.

    Example: ``20260627T1530-a1b2c3d4``.

    The timestamp is UTC. The UUID suffix is the first 8 hex characters
    of a UUID4 (sufficient for uniqueness within a single wall-clock
    second; the trailing nanosecond-and-clock skew protects against
    collisions at sub-second rates).
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M")
    # First 8 hex chars of a fresh UUID4 — adequate for uniqueness
    # within a single second. ``secrets`` is used here only as a
    # source of entropy; we are not relying on its CSPRNG properties
    # specifically.
    suffix = uuid.UUID(int=secrets.randbits(128)).hex[:8]
    return f"{timestamp}-{suffix}"
