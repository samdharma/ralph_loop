"""Stage failure reporting and design-spec summarization.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, helpers that write failure
reports, extract failure summaries, and summarize/read design specs live
here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Bootstrap sys.path so ``from core.pipeline...`` and the
# engine module can be resolved when this file is loaded via pytest
# from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.artifacts_ops import _design_spec_path  # noqa: E402
from core.pipeline.shell import PROJECT_ROOT  # noqa: E402


def _write_stage_report(issue_num: int, stage: str, failed_step: str, output: str):
    """Write a failure report file following the Failure Reporting Contract."""
    report_path = PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Truncate if enormous (GitHub comments already have their own limit)
    max_output = 50000
    if len(output) > max_output:
        output = (
            output[:max_output].rstrip() + "\n\n_(output truncated for report file)_"
        )
    report = (
        f"# Failure Report: Stage {stage}\n\n"
        f"## Stage\n"
        f"{stage} — {failed_step}\n\n"
        f"## What Was Attempted\n"
        f"Pipeline ran the {failed_step} step for issue #{issue_num}.\n\n"
        f"## What Failed\n\n"
        f"```\n{output}\n```\n\n"
        f"## Root Cause\n"
        f"See the output above for the specific test/lint failures.\n\n"
        f"## What to Check\n"
        f"- The full report is at `.ralph/issue-{issue_num}-report.md`\n"
        f"- Design spec: `docs/designs/{issue_num}.md`\n"
        f"- QA-written tests: `.ralph/issue-{issue_num}-tests.json`\n"
    )
    report_path.write_text(report, encoding="utf-8")
    print(f"[ralph] Failure report written to {report_path}")


def _extract_failure_summary(stdout: str, stderr: str) -> str:
    """Extract the most relevant failure lines from validation output."""
    combined = (stdout + "\n" + stderr).strip()
    if not combined:
        return "(no output captured from validation gate)"

    lines = combined.splitlines()
    summary_lines: list[str] = []

    # Determine what failed — add a header line for clarity
    has_test_failure = any("pytest" in line and "FAILED" in line for line in lines)
    has_lint_failure = any(
        f"{tool} FAILED" in line
        for tool in ["black", "isort", "flake8", "ruff", "mypy"]
        for line in lines
    )

    if has_test_failure and not has_lint_failure:
        summary_lines.append(
            "═══ Validation failed: TESTS did not pass (lint checks were skipped) ═══"
        )
        summary_lines.append("")
    elif has_test_failure and has_lint_failure:
        summary_lines.append("═══ Validation failed: TESTS and LINT both failed ═══")
        summary_lines.append("")
    elif has_lint_failure:
        summary_lines.append(
            "═══ Validation failed: LINT checks failed on modified files ═══"
        )
        summary_lines.append("")

    # Always include FAILED lines and their surrounding context
    include_next = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Markers that indicate a failure we want to capture
        is_failure = any(
            marker in stripped
            for marker in [
                "FAILED",
                "ERROR",
                "FAIL",
                "assert",
                "AssertionError",
                "E ",  # pytest error context lines
                "RALPH_GATE_FAILED",
                "error:",
            ]
        )
        if is_failure or include_next > 0:
            summary_lines.append(line)
            include_next = 3 if is_failure else include_next - 1

    if not summary_lines:
        # Fallback: return last 30 lines
        summary_lines = lines[-30:]

    result = "\n".join(summary_lines)
    # Truncate summary for GitHub comment
    max_summary = 8000
    if len(result) > max_summary:
        result = (
            result[:max_summary].rstrip()
            + "\n\n_(summary truncated — see `.ralph/issue-*-report.md` for full output)_"
        )
    return result


def _summarize_design_spec(issue_num: int) -> Optional[str]:
    """Read the per-issue design spec and return a condensed design summary
    for posting as a GitHub issue comment.

    Reads from docs/designs/<issue_num>.md only. After A7.1, the legacy
    fallback is removed; v3 projects must run `ralph migrate`
    to convert their legacy design content.
    """
    design_file = _design_spec_path(issue_num)
    if not design_file.exists():
        return None
    text = design_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = ""
    summary_parts: list[str] = []
    decisions: list[str] = []
    risks: list[str] = []
    ac_count = 0
    section: Optional[str] = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped.lstrip("# ").strip()
            continue
        if stripped.startswith("## Summary"):
            section = "summary"
            continue
        if stripped.startswith("## Design Decisions"):
            section = "decisions"
            continue
        if stripped.startswith("## Acceptance Criteria"):
            section = "criteria"
            continue
        if stripped.startswith("## Risks"):
            section = "risks"
            continue
        if stripped.startswith("## ") or stripped.startswith("# "):
            section = None
            continue
        if section == "summary" and stripped:
            summary_parts.append(stripped)
        if section == "decisions" and stripped and stripped[0] in "0123456789-":
            decisions.append(stripped)
        if section == "criteria" and stripped.startswith("- ["):
            ac_count += 1
        if section == "risks" and stripped and stripped.startswith("- "):
            risks.append(stripped)

    if not title:
        return None

    out = ["## 📐 Design Complete", ""]
    out.append(f"**{title}**")
    out.append("")
    if summary_parts:
        out.append(f"**Summary:** {' '.join(summary_parts)}")
        out.append("")
    if design_file.exists():
        out.append(
            f"**Files:** See [`docs/designs/{issue_num}.md`](docs/designs/{issue_num}.md)"
        )
    else:
        out.append(
            f"**Files:** See [`docs/designs/{issue_num}.md`](docs/designs/{issue_num}.md) (legacy fallback removed in A7.1)"
        )
    if decisions:
        out.append("")
        out.append("**Key Decisions:**")
        for d in decisions:
            out.append(f"- {d}")
    if risks:
        out.append("")
        out.append("**Risks:**")
        for r in risks:
            out.append(r)
    out.append("")
    out.append(f"**Acceptance Criteria:** {ac_count} criteria defined.")
    out.append("")
    if design_file.exists():
        out.append(f"Full design spec committed to `docs/designs/{issue_num}.md`.")
    else:
        out.append(
            f"Full design spec expected at `docs/designs/{issue_num}.md` (not yet written)."
        )
    return "\n".join(out)


def _read_partial_design_spec(issue_num: int, max_chars: int = 2000) -> Optional[str]:
    """Read the per-issue design spec if it exists.

    Returns truncated content or None if the file is missing. The legacy
    fallback is removed in A7.1; v3 projects must run `ralph migrate`.
    """
    design_file = _design_spec_path(issue_num)
    if not design_file.exists():
        return None
    text = design_file.read_text(encoding="utf-8")
    try:
        text = text.strip()
        if not text:
            return None
        if len(text) > max_chars:
            text = (
                text[:max_chars].rstrip()
                + "\n\n_(truncated — see file for full content)_"
            )
        return text
    except Exception:
        return None


def _format_stage_failure(
    stage: str,
    partial_spec: Optional[str] = None,
    report_content: Optional[str] = None,
    fallback: str = "Blocking issue.",
    issue_num: Optional[int] = None,
    agent_stdout: Optional[str] = None,
) -> str:
    """Build a detailed stage-failure comment with pointers to artifacts.

    Per spec §10.1 A5: the failure comment includes:
    - Last 50 lines of agent stdout (when available)
    - Link to trajectory file (when present)
    - Link to failure report file

    The function is idempotent: re-formatting the same failure produces
    the same body.
    """
    lines = [f"❌ {stage} stage failed.", ""]
    lines.append("See the design spec for this issue (at `docs/designs/<N>.md`).")
    if partial_spec:
        lines.append("")
        lines.append("## Partial Design Spec")
        lines.append("")
        lines.append(partial_spec)
    if report_content:
        lines.append("")
        lines.append("## Failure Details")
        lines.append("")
        # Truncate to fit GitHub comments (65k char limit)
        max_detail = 50000
        if len(report_content) > max_detail:
            report_content = (
                report_content[:max_detail].rstrip()
                + "\n\n_(output truncated — see `.ralph/issue-*-report.md` for full log)_"
            )
        lines.append(report_content)
    else:
        lines.append("")
        lines.append(fallback)

    # A5.1: Agent stdout (last 50 lines) when provided.
    if agent_stdout:
        lines.append("")
        lines.append("## Agent stdout (last 50 lines)")
        lines.append("")
        tail = "\n".join(agent_stdout.splitlines()[-50:])
        lines.append("```")
        lines.append(tail)
        lines.append("```")

    # A5.1: Trajectory file link when present (issue_num and file must be set).
    if issue_num is not None:
        traj_path = (
            PROJECT_ROOT / ".ralph" / "issues" / str(issue_num) / "trajectory.jsonl"
        )
        if traj_path.exists():
            rel = traj_path.relative_to(PROJECT_ROOT)
            lines.append("")
            lines.append("## Trajectory")
            lines.append("")
            lines.append(f"Full trajectory: [`{rel}`]({rel})")

        # A5.1: Failure report link (always — the report is written by _write_stage_report).
        rel_report = Path(f".ralph/issue-{issue_num}-report.md")
        lines.append("")
        lines.append("## Failure report")
        lines.append("")
        lines.append(f"Full report: [`{rel_report}`]({rel_report})")

    return "\n".join(lines)


__all__ = [
    "_write_stage_report",
    "_extract_failure_summary",
    "_format_stage_failure",
    "_summarize_design_spec",
    "_read_partial_design_spec",
]
