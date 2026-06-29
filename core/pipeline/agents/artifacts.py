"""Artifact directory writer for the per-issue layout.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.2 and §10.1 A3 (R1 — artifact handoff):

Each issue has a dedicated directory at `.ralph/issues/<N>/artifacts/` where
the DESIGN stage writes structured inputs that the IMPLEMENT stage reads.
This replaces the v3 `--continue` session-based handoff.

Layout:
    .ralph/issues/<N>/
        artifacts/
            design.md                  - Markdown design spec
            files_in_scope.json        - List of paths the implementer may touch
            acceptance_criteria.json   - List of {id, criterion} AC objects
            qa_tests_to_pass.json      - List of test node IDs to satisfy

All write_* functions are idempotent on re-write. The parent directories
are created as needed. Returns the absolute Path of the written file.

This module also provides typed read/write helpers built on the Pydantic
models in :mod:`core.schemas.artifacts`. The original file-level writers
remain unchanged in signature so existing callers keep working.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.schemas.artifacts import (
    AcceptanceCriterion,
    DesignArtifact,
    TestArtifact,
)

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


def _artifact_dir(issue_num: int, project_root: Path | None = None) -> Path:
    """Compute the artifact directory for a given issue number."""
    root = project_root if project_root is not None else PROJECT_ROOT
    return root / ".ralph" / "issues" / str(issue_num) / "artifacts"


def _write(path: Path, content: str) -> Path:
    """Write `content` to `path`, creating parent directories. Idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def write_design(
    issue_num: int, design_text: str, project_root: Path | None = None
) -> Path:
    """Write the design spec to `<artifact_dir>/design.md`.

    Args:
        issue_num: GitHub issue number.
        design_text: Markdown content of the design spec.
        project_root: Override the project root (defaults to PROJECT_ROOT).
            Useful for tests.

    Returns:
        Absolute Path to the written design.md file.
    """
    return _write(_artifact_dir(issue_num, project_root) / "design.md", design_text)


def write_files_in_scope(
    issue_num: int, paths: list[str], project_root: Path | None = None
) -> Path:
    """Write the in-scope file paths to `<artifact_dir>/files_in_scope.json`."""
    return _write(
        _artifact_dir(issue_num, project_root) / "files_in_scope.json",
        json.dumps(paths, indent=2),
    )


def write_acceptance_criteria(
    issue_num: int, ac: list[dict[str, Any]], project_root: Path | None = None
) -> Path:
    """Write the acceptance criteria list to `<artifact_dir>/acceptance_criteria.json`.

    Each AC must be a dict with at least `id` and `criterion` keys.
    The dicts are validated against :class:`core.schemas.artifacts.AcceptanceCriterion`
    before writing so malformed input fails fast with a clear error.
    """
    normalized = []
    for item in ac:
        if not isinstance(item, dict):
            raise TypeError(f"AC must be a dict; got {type(item).__name__}")
        criterion = AcceptanceCriterion.model_validate(item)
        normalized.append(criterion.model_dump(mode="json"))
    return _write(
        _artifact_dir(issue_num, project_root) / "acceptance_criteria.json",
        json.dumps(normalized, indent=2),
    )


def write_qa_tests(
    issue_num: int, qa_tests: list[str], project_root: Path | None = None
) -> Path:
    """Write the QA tests list to `<artifact_dir>/qa_tests_to_pass.json`."""
    return _write(
        _artifact_dir(issue_num, project_root) / "qa_tests_to_pass.json",
        json.dumps(qa_tests, indent=2),
    )


def write_design_artifact(
    design: DesignArtifact, project_root: Path | None = None
) -> dict[str, Path]:
    """Persist a :class:`DesignArtifact` to the per-issue artifact directory.

    Writes ``design.md``, ``files_in_scope.json``, and
    ``acceptance_criteria.json``. Returns a mapping from artifact name to
    the absolute Path of the written file.
    """
    issue_num = design.issue_num
    paths: dict[str, Path] = {
        "design": write_design(issue_num, design.design_text, project_root),
        "files_in_scope": write_files_in_scope(
            issue_num, design.files_in_scope, project_root
        ),
        "acceptance_criteria": write_acceptance_criteria(
            issue_num,
            [
                criterion.model_dump(mode="json")
                for criterion in design.acceptance_criteria
            ],
            project_root,
        ),
    }
    return paths


def read_design_artifact(
    issue_num: int, project_root: Path | None = None
) -> DesignArtifact:
    """Load a :class:`DesignArtifact` from the per-issue artifact directory.

    Inverse of :func:`write_design_artifact`. Missing files are treated as
    empty (``design_text`` defaults to ``""`` and list fields default to
    ``[]``), which keeps the reader resilient while still validating the
    shape of any data that is present.
    """
    art_dir = _artifact_dir(issue_num, project_root)
    design_path = art_dir / "design.md"
    files_path = art_dir / "files_in_scope.json"
    ac_path = art_dir / "acceptance_criteria.json"

    design_text = design_path.read_text() if design_path.exists() else ""
    files_in_scope: list[str] = (
        json.loads(files_path.read_text()) if files_path.exists() else []
    )
    raw_ac: list[dict[str, Any]] = (
        json.loads(ac_path.read_text()) if ac_path.exists() else []
    )
    acceptance_criteria = [AcceptanceCriterion.model_validate(item) for item in raw_ac]

    return DesignArtifact(
        issue_num=issue_num,
        design_text=design_text,
        files_in_scope=files_in_scope,
        acceptance_criteria=acceptance_criteria,
    )


def write_test_artifact(test: TestArtifact, project_root: Path | None = None) -> Path:
    """Persist a :class:`TestArtifact` to ``qa_tests_to_pass.json``."""
    return write_qa_tests(test.issue_num, test.qa_tests, project_root)


def read_test_artifact(
    issue_num: int, project_root: Path | None = None
) -> TestArtifact:
    """Load a :class:`TestArtifact` from ``qa_tests_to_pass.json``.

    Inverse of :func:`write_test_artifact`. Missing file is treated as an
    empty test list.
    """
    art_dir = _artifact_dir(issue_num, project_root)
    qa_path = art_dir / "qa_tests_to_pass.json"
    qa_tests: list[str] = json.loads(qa_path.read_text()) if qa_path.exists() else []
    return TestArtifact(issue_num=issue_num, qa_tests=qa_tests)
