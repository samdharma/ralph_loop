"""CheckpointState Pydantic model (per spec §6.1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1:
    > core/schemas/checkpoint.py — CheckpointState model

The companion ``save_checkpoint`` / ``clear_checkpoint`` /
``recover_from_crash`` functions live at
``core/pipeline/checkpoint.py`` (C1.7a).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CheckpointState(BaseModel):
    """Typed checkpoint state for crash recovery (per spec §6.1).

    Captures the minimum state needed to resume a pipeline run after
    a daemon crash: the issue number, the current stage, the commit
    SHA at which the issue was claimed, and the run_id for
    idempotency. Pydantic v2 model per spec §4.2.
    """

    model_config = ConfigDict(frozen=False)

    issue_num: int = Field(..., description="GitHub issue number")
    stage: str = Field(..., description="Pipeline stage at checkpoint")
    pre_sha: str = Field(
        default="",
        description="Commit SHA at which the issue was claimed",
    )
    run_id: str = Field(
        default="",
        description="Run identifier for idempotency",
    )
