"""Sub-agent and stage prompt assembly.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the helpers that build prompts
for the DESIGN/TEST/IMPLEMENT/VERIFY stages live here.
"""

from __future__ import annotations

import json
import re
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

from core.pipeline.artifacts_ops import _design_spec_path  # noqa: E402
from core.pipeline.shell import PROJECT_ROOT, PROMPT_FILE, PROMPTS_DIR, gh  # noqa: E402


def _fetch_issue_comments(issue_num: int, limit: int = 2) -> str:
    """Fetch the last N comments from the GitHub issue. Returns formatted markdown."""
    try:
        result = gh(
            "issue", "view", str(issue_num), "--json", "comments", "--jq", ".comments"
        )
        comments = json.loads(result.stdout)
        if not isinstance(comments, list):
            return ""
        comments.sort(key=lambda c: c.get("createdAt", "") or "")
        selected = comments[-limit:] if len(comments) >= limit else comments
        if not selected:
            return ""
        lines = [f"\n\n## Recent Issue Comments (last {len(selected)})"]
        for idx, c in enumerate(selected, 1):
            author = c.get("author", {}).get("login", "unknown")
            created = c.get("createdAt", "")
            body = c.get("body", "") or ""
            lines.append(f"\n### Comment {idx} by @{author} ({created})\n\n{body}")
        lines.append(
            "\n*If these comments do not provide enough clarity, read additional "
            "comments before proceeding.*"
        )
        return "\n".join(lines)
    except Exception as e:
        print(f"[ralph] WARNING: could not fetch comments for #{issue_num}: {e}")
        return ""


def _assemble_subagent_prompt(issue: dict, stage_prompt_file: str, mode: str) -> str:
    """
    Build a prompt for a sub-agent invocation.

    Mode A (Isolated): issue body + design spec + stage persona + recent comments.
      No codebase context, no reference docs. Fresh pi --print session.
      Used for TEST and VERIFY sub-agents — genuine independent perspective.

    Mode B (Artifact-based): issue body + DESIGN artifacts + stage persona + recent comments.
      Context is carried by the artifact directory, not by a continued session.
      Used for IMPLEMENT sub-agent — builds on DESIGN's codebase knowledge.
    """
    base = ""
    if PROMPT_FILE.exists():
        base = PROMPT_FILE.read_text(encoding="utf-8")

    # Stage-specific persona instructions
    stage_prompt = ""
    stage_path = PROMPTS_DIR / stage_prompt_file
    if stage_path.exists():
        stage_prompt = stage_path.read_text(encoding="utf-8")

    body = issue.get("body") or "(No description)"

    # Build prompt sections
    section_label = (
        "Sub-Agent Instructions"
        if mode == "A"
        else "Sub-Agent Instructions (Mode B — continuing from DESIGN artifacts)"
    )
    prompt = (
        f"{base}\n\n"
        f"---\n\n"
        f"## {section_label}\n\n"
        f"{stage_prompt}\n\n"
        f"---\n\n"
        f"## Issue #{issue['number']}: {issue['title']}\n\n"
        f"{body}"
    )

    # Design spec — read per-issue file. Legacy fallback removed in A7.1.
    # Injected in both Mode A and Mode B so the prompt is self-contained.
    design_file = _design_spec_path(issue["number"])
    if design_file.exists():
        design_spec = design_file.read_text(encoding="utf-8")
        prompt += (
            f"\n\n## Design Spec (from DESIGN stage)\n\n"
            f"{design_spec}\n\n"
            f"_Source: `docs/designs/{issue['number']}.md` — "
            f"this is the design for the current issue only._"
        )

    # A3.2: artifact-based handoff for IMPLEMENT sub-agent (Mode B).
    # The IMPLEMENT agent reads its inputs from disk, not from session context.
    if mode == "B":
        artifact_dir = (
            PROJECT_ROOT / ".ralph" / "issues" / str(issue["number"]) / "artifacts"
        )
        if not artifact_dir.is_dir():
            # Per task A-021 acceptance criteria: fail fast, no silent fallback.
            raise FileNotFoundError(
                f"Artifact directory missing: {artifact_dir}. "
                "The DESIGN stage must write artifacts before IMPLEMENT can run. "
                "See docs/IMPROVEMENT_ROADMAP_SPEC.md §6.2."
            )
        design_artifact = artifact_dir / "design.md"
        files_in_scope_artifact = artifact_dir / "files_in_scope.json"
        acceptance_criteria_artifact = artifact_dir / "acceptance_criteria.json"
        qa_tests_artifact = artifact_dir / "qa_tests_to_pass.json"

        prompt += "\n\n## Implement Inputs (from DESIGN artifacts)\n"
        prompt += (
            f"\n_All inputs below are read from `.ralph/issues/"
            f"{issue['number']}/artifacts/`. Per spec §6.2, this replaces "
            f"the v3 `--continue` session-based handoff._\n"
        )

        if design_artifact.exists():
            prompt += f"\n### Design\n\n{design_artifact.read_text(encoding='utf-8')}\n"

        if files_in_scope_artifact.exists():
            import json as _json

            paths = _json.loads(files_in_scope_artifact.read_text(encoding="utf-8"))
            prompt += "\n### Files In Scope (you may modify ONLY these)\n\n"
            for p in paths:
                prompt += f"- `{p}`\n"

        if acceptance_criteria_artifact.exists():
            import json as _json

            acs = _json.loads(acceptance_criteria_artifact.read_text(encoding="utf-8"))
            prompt += "\n### Acceptance Criteria\n\n"
            for idx, ac in enumerate(acs, 1):
                prompt += (
                    f"{idx}. **[{ac.get('id', 'AC')}]** {ac.get('criterion', '')}\n"
                )

        if qa_tests_artifact.exists():
            import json as _json

            qa = _json.loads(qa_tests_artifact.read_text(encoding="utf-8"))
            prompt += "\n### QA Tests to Pass\n\n"
            for t in qa:
                prompt += f"- `{t}`\n"

    # Reference docs (all modes)
    ref_docs = _parse_reference_docs(body)
    if ref_docs:
        prompt += "\n\n## Reference Documentation\n\n"
        for ref in ref_docs:
            ref_path = PROJECT_ROOT / ref
            if ref_path.exists():
                prompt += f"### {ref}\n\n{ref_path.read_text(encoding='utf-8')}\n\n"
            else:
                prompt += f"### {ref}\n\n(File not found: {ref})\n\n"

    # Mode A isolation notice
    if mode == "A":
        prompt += (
            "\n\n---\n\n"
            "**ISOLATION NOTICE:** You are a Mode A sub-agent in a fresh session. "
            "You have NO prior context about the codebase. "
            "Do NOT attempt to read implementation code — work from the specification above ONLY."
        )

    # Mode B continuation notice
    if mode == "B":
        prompt += (
            "\n\n---\n\n"
            "**CONTEXT NOTE:** You are a Mode B sub-agent continuing from the DESIGN artifacts. "
            "You inherit full knowledge of the codebase, design decisions, and the issue. "
            "Test files were written by an independent QA sub-agent (Mode A) who never saw the code. "
            "Find the test files in tests/ and implement minimal code to make them pass. "
            "Do NOT write new test files or modify existing tests — the QA tests are the verification truth."
        )

    prompt += _fetch_issue_comments(issue["number"], limit=2)
    return prompt


def assemble_stage_prompt(issue: dict, stage_prompt_file: str) -> str:
    """Build a stage-specific prompt from PROMPT.md + stage persona + issue body."""
    base = ""
    if PROMPT_FILE.exists():
        base = PROMPT_FILE.read_text(encoding="utf-8")

    # Stage-specific persona instructions
    stage_prompt = ""
    stage_path = PROMPTS_DIR / stage_prompt_file
    if stage_path.exists():
        stage_prompt = stage_path.read_text(encoding="utf-8")

    body = issue.get("body") or "(No description)"

    # Append reference docs if referenced in body
    ref_docs = _parse_reference_docs(body)
    ref_section = ""
    if ref_docs:
        ref_section = "\n\n## Reference Documentation\n\n"
        for ref in ref_docs:
            ref_path = PROJECT_ROOT / ref
            if ref_path.exists():
                ref_section += (
                    f"### {ref}\n\n{ref_path.read_text(encoding='utf-8')}\n\n"
                )
            else:
                ref_section += f"### {ref}\n\n(File not found: {ref})\n\n"

    prompt = (
        f"{base}\n\n"
        f"---\n\n"
        f"## Stage Instructions\n\n"
        f"{stage_prompt}\n\n"
        f"---\n\n"
        f"## Issue #{issue['number']}: {issue['title']}\n\n"
        f"{body}"
        f"{ref_section}"
    )
    prompt += _fetch_issue_comments(issue["number"], limit=2)
    return prompt


def _parse_reference_docs(body: str) -> list[str]:
    """Extract 'Reference: path/to/doc.md' from issue body."""
    refs = []
    for line in body.splitlines():
        match = re.search(r"Reference:\s*(\S+)", line, re.IGNORECASE)
        if match:
            refs.append(match.group(1))
    return refs


__all__ = [
    "_assemble_subagent_prompt",
    "assemble_stage_prompt",
    "_parse_reference_docs",
    "_fetch_issue_comments",
]
