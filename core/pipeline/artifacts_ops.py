"""Per-issue artifact path helpers and cleanup/archive routines.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, helpers for design-spec paths
and artifact cleanup/archival live here so prompt/report helpers can
reference them without importing ``core/engine.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap sys.path so ``from core.pipeline...`` and the
# engine module can be resolved when this file is loaded via pytest
# from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.agents.artifacts import (  # noqa: E402
    write_acceptance_criteria,
    write_design,
    write_files_in_scope,
    write_qa_tests,
)
from core.pipeline.shell import DESIGN_SPEC_DIR, PROJECT_ROOT  # noqa: E402
from core.pipeline.test_tracking import _test_tracking_file  # noqa: E402


def _design_spec_path(issue_num: int) -> Path:
    """Return the path to the per-issue design spec for issue_num."""
    return DESIGN_SPEC_DIR / f"{issue_num}.md"


def _parse_affected_files(design_text: str) -> list[str]:
    """Extract file paths from the ``## Affected Files`` section.

    Accepts bullets like ``- `src/foo.py` — description`` and returns
    the bare paths. Non-existent sections return an empty list.
    """
    in_section = False
    files: list[str] = []
    for line in design_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## affected"):
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped.startswith("-"):
            continue
        # Extract first backtick-delimited path.
        parts = stripped.split("`")
        if len(parts) >= 3:
            candidate = parts[1]
            if candidate and not candidate.isspace():
                files.append(candidate)
    return files


def _parse_acceptance_criteria(design_text: str) -> list[dict[str, str]]:
    """Extract criteria from the ``## Acceptance Criteria`` section.

    Accepts bullets like ``- [ ] criterion text`` or ``- criterion text``.
    Returns a list of ``{"id": "AC<N>", "criterion": "..."}`` dicts.
    """
    in_section = False
    criteria: list[dict[str, str]] = []
    for line in design_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## acceptance"):
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped.startswith("-"):
            continue
        # Drop optional checkbox marker.
        text = stripped[1:].strip()
        if text.startswith("[") and "]" in text:
            text = text.split("]", 1)[1].strip()
        if text:
            criteria.append({"id": f"AC{len(criteria) + 1}", "criterion": text})
    return criteria


def write_design_artifacts(issue_num: int, design_text: str) -> None:
    """Write the per-issue artifact directory for the IMPLEMENT stage.

    Per spec §6.2 and §10.1 A3 (R1), the DESIGN stage writes:
      - ``.ralph/issues/<N>/artifacts/design.md``
      - ``.ralph/issues/<N>/artifacts/files_in_scope.json``
      - ``.ralph/issues/<N>/artifacts/acceptance_criteria.json``
      - ``.ralph/issues/<N>/artifacts/qa_tests_to_pass.json`` (empty;
        populated by the TEST stage)
    """
    files = _parse_affected_files(design_text)
    criteria = _parse_acceptance_criteria(design_text)
    write_design(issue_num, design_text)
    write_files_in_scope(issue_num, files)
    write_acceptance_criteria(issue_num, criteria)
    write_qa_tests(issue_num, [])


def _archived_issue_dir(issue_num: int) -> Path:
    """Return the archive directory for a blocked issue's artifacts."""
    return PROJECT_ROOT / ".ralph" / "blocked" / f"issue-{issue_num}"


def _cleanup_issue_artifacts(issue_num: int):
    """Remove per-issue test-tracking files after pipeline SUCCEEDS.

    On failure, artifacts are MOVED to .ralph/blocked/issue-N/ instead of
    being deleted, so a human can inspect the evidence.
    """
    tracking_file = _test_tracking_file(issue_num)
    if tracking_file.exists():
        tracking_file.unlink()
        print(f"[ralph] Cleaned up test tracking: {tracking_file.name}")


def _archive_issue_artifacts(issue_num: int):
    """Move test-tracking files to .ralph/blocked/ for inspection."""
    archive_dir = _archived_issue_dir(issue_num)
    archive_dir.mkdir(parents=True, exist_ok=True)

    tracking_file = _test_tracking_file(issue_num)
    if tracking_file.exists():
        dest = archive_dir / tracking_file.name
        tracking_file.rename(dest)
        print(f"[ralph] Archived test tracking: {tracking_file.name} → blocked/")

    # Also copy the failure report if it exists
    report_file = PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-report.md"
    if report_file.exists():
        dest = archive_dir / report_file.name
        report_file.rename(dest)
        print(f"[ralph] Archived failure report: {report_file.name} → blocked/")


__all__ = [
    "_design_spec_path",
    "_archived_issue_dir",
    "_cleanup_issue_artifacts",
    "_archive_issue_artifacts",
]
