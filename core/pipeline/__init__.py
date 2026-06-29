"""Core pipeline package — public API re-exports.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, §10.3 C1:
    > core/pipeline/ — NEW in C1: state, runner, stages, agents, github,
    >                  checkpoint, metrics, recovery

This ``__init__.py`` re-exports the public surface so that callers
can do ``from core.pipeline import run_loop, Stage, ...``. Per
spec §9.1.2 (preserve the public ralph CLI surface additive only),
the engine module continues to expose the same symbols.

Re-exported symbols:

  - run_loop, run_pipeline                (runner.py)
  - Stage, PipelineState, STATUS_LABEL   (state.py)
  - generate_run_id                       (state.py)
  - DesignStage, BuildStage, VerifyStage (stages/)
  - Stage (ABC)                          (stages/base.py)
  - AgentBase, PiAgent, KimiAgent        (agents/)
  - create_worktree, remove_worktree     (agents/base.py)
  - GitHubClient                         (github/client.py)
  - transition_label, gh_comment         (github/{labels,comments}.py)
  - sync_status, sync_closed             (github/board.py)
  - save_checkpoint, clear_checkpoint,
    recover_from_crash                    (checkpoint.py)
  - append_trajectory_event, read_trajectory (metrics.py)
  - CheckpointState                      (core.schemas.checkpoint)
"""

from __future__ import annotations

# Agents
from core.pipeline.agents.base import (  # noqa: F401
    AgentBase,
    create_worktree,
    remove_worktree,
)
from core.pipeline.agents.kimi import KimiAgent  # noqa: F401
from core.pipeline.agents.pi import PiAgent  # noqa: F401

# Checkpoint / metrics / recovery
from core.pipeline.checkpoint import (  # noqa: F401
    clear_checkpoint,
    recover_from_crash,
    save_checkpoint,
)

# Runner
from core.pipeline.daemon import run_loop  # noqa: F401
from core.pipeline.github.board import sync_closed, sync_status  # noqa: F401

# GitHub
from core.pipeline.github.client import GitHubClient  # noqa: F401
from core.pipeline.github.comments import gh_comment  # noqa: F401
from core.pipeline.github.labels import transition_label  # noqa: F401
from core.pipeline.metrics import (  # noqa: F401
    append_trajectory_event,
    read_trajectory,
)
from core.pipeline.recovery import recover_from_crash as _recovery_fn  # noqa: F401
from core.pipeline.runner import run_pipeline  # noqa: F401

# Stages
from core.pipeline.stages.base import Stage as StageABC  # noqa: F401
from core.pipeline.stages.build import BuildStage  # noqa: F401
from core.pipeline.stages.design import DesignStage  # noqa: F401
from core.pipeline.stages.verify import VerifyStage  # noqa: F401

# State
from core.pipeline.state import (  # noqa: F401
    STATUS_LABEL,
    PipelineState,
    Stage,
    generate_run_id,
)

# Schemas
from core.schemas.checkpoint import CheckpointState  # noqa: F401

__all__ = [
    # state
    "Stage",
    "PipelineState",
    "STATUS_LABEL",
    "generate_run_id",
    # runner
    "run_loop",
    "run_pipeline",
    # stages
    "StageABC",
    "DesignStage",
    "BuildStage",
    "VerifyStage",
    # agents
    "AgentBase",
    "PiAgent",
    "KimiAgent",
    "create_worktree",
    "remove_worktree",
    # github
    "GitHubClient",
    "transition_label",
    "gh_comment",
    "sync_status",
    "sync_closed",
    # checkpoint/metrics/recovery
    "save_checkpoint",
    "clear_checkpoint",
    "recover_from_crash",
    "append_trajectory_event",
    "read_trajectory",
    # schemas
    "CheckpointState",
]
