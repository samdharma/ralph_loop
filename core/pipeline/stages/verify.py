"""VERIFY stage (C1.4c — per plan §1.1 C1.4).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the VERIFY stage lives at
``core/pipeline/stages/verify.py``. It runs the independent reviewer
sub-agent in Mode A (isolated) and then executes the validation gate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

# Bootstrap sys.path so ``from core.pipeline...`` modules can be resolved
# when this file is loaded via pytest from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.agents.base import (  # noqa: E402
    WorktreeError,
    create_worktree,
    remove_worktree,
)
from core.pipeline.agents.pi import invoke_agent  # noqa: E402
from core.pipeline.git_ops import _has_commits  # noqa: E402
from core.pipeline.github.comments import gh_comment  # noqa: E402
from core.pipeline.prompts import _assemble_subagent_prompt  # noqa: E402
from core.pipeline.reporting import (  # noqa: E402
    _extract_failure_summary,
    _format_stage_failure,
    _write_stage_report,
)
from core.pipeline.retry import log_metrics  # noqa: E402
from core.pipeline.shell import gh, git, run  # noqa: E402
from core.pipeline.stages.base import Stage  # noqa: E402
from core.pipeline.test_tracking import (  # noqa: E402
    _load_test_tracking,
    _resolve_existing_test_paths,
)


def run_verify_stage(issue: dict) -> bool:
    """
    STAGE 3: VERIFY — Mode A isolated sub-agent.
    Fresh session. Sees only: issue + design spec + git diff.
    Does 5-axis review + validation gate.

    Per spec §10.2 B3, the agent runs inside a git worktree so it
    cannot corrupt the parent repo. ``create_worktree`` runs first;
    ``remove_worktree`` runs in a finally block to survive failures.
    """
    issue_num = issue["number"]

    print(f"\n[ralph] STAGE 3/3: VERIFY for #{issue_num}")
    gh_comment(issue_num, "🔍 VERIFY stage started (independent review).")
    log_metrics(
        "stage_start", issue=str(issue_num), stage="verify", subagent="verify", mode="A"
    )

    wt_path: Optional[Path] = None
    try:
        wt_path = create_worktree(issue_num)
    except WorktreeError as e:
        # Worktree isolation is a hard requirement (Phase D follow-up B3).
        # Do not fall back to the repo root; block the issue instead.
        print(f"[ralph] ERROR: worktree creation failed for #{issue_num}: {e}")
        gh_comment(
            issue_num,
            "🚫 VERIFY blocked: unable to create isolated git worktree. "
            "Worktree isolation is required; check daemon logs for details.",
        )
        log_metrics(
            "worktree_failed",
            issue=str(issue_num),
            subagent="verify",
            detail=str(e),
        )
        return False

    final_success: bool = False
    try:
        # Get the git diff for the reviewer to inspect
        pre_sha = (
            git("rev-parse", "HEAD~1").stdout.strip()
            if _has_commits()
            else git("rev-parse", "HEAD").stdout.strip()
        )
        diff = git("diff", pre_sha, "HEAD").stdout if _has_commits() else ""

        # Mode A: assemble prompt with minimal context (no codebase reference)
        prompt = _assemble_subagent_prompt(issue, "verify.md", mode="A")

        # Include git diff
        if diff:
            prompt += (
                f"\n\n## Git Diff (changes to review)\n\n```diff\n{diff[:8000]}\n```"
            )
            if len(diff) > 8000:
                prompt += "\n\n(…diff truncated — review key files from the repo)"

        agent_ok = invoke_agent(prompt, issue_num)
        if agent_ok:
            gh_comment(issue_num, "✅ VERIFY review sub-agent completed.")
        else:
            gh_comment(issue_num, "❌ VERIFY review sub-agent failed.")

        # Determine the agent's own verdict by checking the last issue comment.
        # The agent writes "## Overall: PASS" or "## Overall: FAIL" per the verify.md prompt.
        agent_verdict_pass: Optional[bool] = None
        try:
            comments_json = gh(
                "issue",
                "view",
                str(issue_num),
                "--json",
                "comments",
                "-q",
                ".comments[-1].body",
            ).stdout
            if (
                '"## Overall: FAIL"' in comments_json
                or '"Overall: FAIL"' in comments_json
            ):
                agent_verdict_pass = False
            elif (
                '"## Overall: PASS"' in comments_json
                or '"Overall: PASS"' in comments_json
            ):
                agent_verdict_pass = True
        except Exception:
            pass

        # The stage passes only if BOTH the agent exited 0 AND the agent's
        # textual verdict is PASS (no override means we trust the exit code).
        if agent_verdict_pass is False:
            print("[ralph] VERIFY agent returned FAIL verdict — forcing stage failure")
            gh_comment(issue_num, "❌ VERIFY review failed — agent reported FAIL. ")
            success = False
        else:
            success = agent_ok

        log_metrics(
            "subagent_complete",
            issue=str(issue_num),
            subagent="verify",
            mode="A",
            result="success" if success else "failure",
            agent_verdict=(
                "fail"
                if agent_verdict_pass is False
                else "pass" if agent_verdict_pass else "unknown"
            ),
        )

        # Run validation gate after review
        if success:
            print("\n[ralph] Running validation gate...")
            core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parents[2]))
            qa_tests = _load_test_tracking(issue_num)
            qa_tests = [
                t for t in qa_tests if t.endswith(".py") and "__pycache__" not in t
            ]  # Defense: skip cache artifacts
            qa_tests = _resolve_existing_test_paths(qa_tests)
            if qa_tests:
                print(f"[ralph] Running QA-written tests from TEST stage: {qa_tests}")
                val_result = run(
                    [
                        sys.executable,
                        os.path.join(core_dir, "validate.py"),
                        "--tier",
                        "targeted",
                        "--pytest-paths",
                    ]
                    + qa_tests,
                    check=False,
                    capture=True,
                )
            else:
                print(
                    "[ralph] No QA-written tests detected; falling back to targeted tier"
                )
                val_result = run(
                    [
                        sys.executable,
                        os.path.join(core_dir, "validate.py"),
                        "--tier",
                        "targeted",
                    ],
                    check=False,
                    capture=True,
                )
            success = val_result.returncode == 0
            if success:
                gh_comment(issue_num, "✅ VERIFY validation gate passed.")
            else:
                gh_comment(issue_num, "❌ VERIFY validation gate failed.")
                # Echo output to terminal and capture for report
                val_output = (
                    (val_result.stdout or "") + "\n" + (val_result.stderr or "")
                )
                if val_result.stdout:
                    print(val_result.stdout, end="")
                if val_result.stderr:
                    print(val_result.stderr, end="", file=sys.stderr)
                failure_summary = _extract_failure_summary(
                    val_result.stdout or "", val_result.stderr or ""
                )
                _write_stage_report(
                    issue_num,
                    "VERIFY",
                    "VALIDATION gate",
                    val_output.strip() or "(no output captured)",
                )
                detail = _format_stage_failure(
                    "VERIFY",
                    report_content=failure_summary,
                )
                gh_comment(issue_num, detail)

            log_metrics("stage_complete", issue=str(issue_num), stage="verify")
        final_success = success
    finally:
        if wt_path is not None:
            remove_worktree(wt_path)

    return final_success


class VerifyStage(Stage):
    """VERIFY pipeline stage — runs the reviewer sub-agent."""

    name = "verify"

    def run(self, issue: dict, **kwargs: Any) -> bool:
        """Run the VERIFY stage."""
        return run_verify_stage(issue)


__all__ = ["VerifyStage", "run_verify_stage"]
