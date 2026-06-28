"""Artifact Pydantic models for the per-issue handoff layout.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §4.2 and §6.2:

Each issue has a dedicated directory at ``.ralph/issues/<N>/artifacts/`` where
one stage writes structured data the next stage reads. This module defines the
Pydantic v2 schemas for those artifacts.

Models:

- :class:`AcceptanceCriterion` — one acceptance-criteria entry.
- :class:`DesignArtifact` — everything the DESIGN stage produces for the
  IMPLEMENT stage (``design.md``, ``files_in_scope.json``,
  ``acceptance_criteria.json``).
- :class:`TestArtifact` — the QA test node IDs produced by the TEST stage
  (``qa_tests_to_pass.json``).
- :class:`ImplementationArtifact` — the IMPLEMENT stage's completed work.
  This is a forward-looking schema: v3.1.x does not yet persist a single
  implementation artifact file, but downstream tooling (reporting, verify)
  can use the model to type-check handoff records.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AcceptanceCriterion(BaseModel):
    """Single acceptance-criteria entry.

    Maps to one object in ``acceptance_criteria.json``. Extra keys are
    ignored rather than rejected so the companion writer stays backward
    compatible with callers that may include additional metadata.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(..., description="Short stable identifier, e.g. AC1")
    criterion: str = Field(..., description="Human-readable criterion text")


class DesignArtifact(BaseModel):
    """Complete artifact bundle produced by the DESIGN stage.

    Per spec §6.2 the DESIGN stage writes:
      - ``design.md`` (the full Markdown design spec)
      - ``files_in_scope.json`` (list of paths the implementer may touch)
      - ``acceptance_criteria.json`` (structured AC list)

    This model is the in-memory representation of that bundle. It is not
    stored as a single JSON file; the companion writer functions in
    :mod:`core.pipeline.agents.artifacts` persist each field to its own
    file so implementers can read only what they need.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    issue_num: int = Field(..., description="GitHub issue number")
    design_text: str = Field(..., description="Markdown design spec content")
    files_in_scope: list[str] = Field(
        default_factory=list,
        description="Paths the implementer is allowed to modify",
    )
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        default_factory=list,
        description="Acceptance criteria extracted from the design spec",
    )


class TestArtifact(BaseModel):
    """QA test list produced by the TEST stage.

    Maps to ``qa_tests_to_pass.json``. The TEST stage populates this list
    with pytest node IDs that the IMPLEMENT stage must satisfy.

    ``__test__ = False`` prevents pytest from treating this class as a
    test class because its name starts with ``Test``.
    """

    __test__ = False

    model_config = ConfigDict(extra="forbid", frozen=False)

    issue_num: int = Field(..., description="GitHub issue number")
    qa_tests: list[str] = Field(
        default_factory=list,
        description="Pytest node IDs the implementation must pass",
    )


class ImplementationArtifact(BaseModel):
    """Summary of the IMPLEMENT stage's completed work.

    The v3.1.x pipeline does not yet persist this as a single artifact file,
    but the schema gives downstream reporting and verification a typed record
    to work with. Fields are intentionally minimal: a free-form summary plus
    the files and tests touched by the implementation.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    issue_num: int = Field(..., description="GitHub issue number")
    summary: str = Field(default="", description="Short implementation summary")
    files_changed: list[str] = Field(
        default_factory=list,
        description="Source files modified or created",
    )
    tests_added: list[str] = Field(
        default_factory=list,
        description="Test files added or updated",
    )


__all__ = [
    "AcceptanceCriterion",
    "DesignArtifact",
    "TestArtifact",
    "ImplementationArtifact",
]
