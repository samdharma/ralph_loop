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
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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
    """
    # Normalize: ensure every AC has id and criterion keys.
    normalized = []
    for item in ac:
        if not isinstance(item, dict):
            raise TypeError(f"AC must be a dict; got {type(item).__name__}")
        if "id" not in item or "criterion" not in item:
            raise ValueError(f"AC missing required keys (id, criterion): {item}")
        normalized.append(item)
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
