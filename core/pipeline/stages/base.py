"""Stage base class (C1.4).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1:
    > ``core/pipeline/stages/`` (NEW in C1)
    > - base.py — Stage ABC: artifact_io, run, verify

This module defines the Stage abstract base class. Concrete stages
(DesignStage, BuildStage, VerifyStage) live in design.py, build.py,
and verify.py respectively.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Stage(ABC):
    """Abstract base class for pipeline stages.

    Concrete stages must implement ``run()``. Optional methods
    ``artifact_io()`` and ``verify()`` have default no-op
    implementations that subclasses can override.

    The base class is intentionally minimal — it provides the type
    contract without imposing behavior. Concrete stages (design,
    build, verify) compose helpers from other modules rather than
    inheriting them.
    """

    name: str = ""  # subclass sets; e.g. "design"

    @abstractmethod
    def run(self, issue: dict, **kwargs: Any) -> bool:
        """Run the stage against an issue. Returns True on success."""
        raise NotImplementedError

    def artifact_io(self, issue_num: int) -> Path:
        """Return the artifact directory for this issue. Default: .ralph/."""
        return Path(".ralph") / f"issue-{issue_num}"

    def verify(self, issue: dict, **kwargs: Any) -> bool:
        """Verify the stage's output. Default: no-op (returns True)."""
        return True


__all__ = ["Stage"]
