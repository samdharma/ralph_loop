#!/usr/bin/env python3
"""
Ralph v3 — Pipeline Engine

Core loop: fetch ticket → claim → DESIGN → BUILD → VERIFY → handoff.
Phase 2: 3-stage pipeline with distinct persona prompts per stage.

Usage (via CLI):
    ralph daemon
"""

import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from core.project_sync import sync_closed, sync_status

# Ensure the project root (parent of ``core/``) is on sys.path so
# ``from core.pipeline.state import ...`` works whether engine.py is
# invoked as ``python core/engine.py`` (bin/ralph flow) or as
# ``python -m core.engine``. Without this, the package import fails
# in the bin/ralph flow because only ``core/`` (not its parent) is
# on sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ─────────────────────────────────────────────────────────
# C1.2 — state.py re-imports (per plan §1.1 C1.2)
# ─────────────────────────────────────────────────────────
# The Stage enum, PipelineState Pydantic model, STATUS_LABEL mapping,
# and generate_run_id helper all live at core.pipeline.state (per
# spec §6.1, §7.2). They are re-imported here so existing callers
# that ``from core.engine import Stage`` continue to work. New code
# should import directly from core.pipeline.state.
from core.pipeline.state import PipelineState  # noqa: E402,F401
from core.pipeline.state import (  # noqa: E402,F401
    STATUS_LABEL,
    Stage,
    generate_run_id,
)

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
# CHECKPOINT_FILE lives in core.pipeline.checkpoint (C1 step 2);
# engine.py re-imports it for backward compatibility.
from core.pipeline.checkpoint import CHECKPOINT_FILE  # noqa: E402,F401

# PID_FILE lives in core.pipeline.recovery (C1 step 3); engine.py
# re-imports it for backward compatibility.
from core.pipeline.recovery import PID_FILE  # noqa: E402,F401

LOG_DIR = PROJECT_ROOT / "logs"
METRICS_FILE = LOG_DIR / "ralph_metrics.jsonl"
PROMPT_FILE = PROJECT_ROOT / "docs" / "agent" / "PROMPT.md"
PROMPTS_DIR = PROJECT_ROOT / "docs" / "agent" / "prompts"

# Per-issue design specs live in docs/designs/<N>.md (one file per issue).
DESIGN_SPEC_DIR = PROJECT_ROOT / "docs" / "designs"
PREFLIGHT_SCRIPT = PROJECT_ROOT / "config" / "ralph_preflight.sh"

# Backoff used when all available agents are rate-limited.
RATE_LIMIT_BACKOFF_SECONDS = 15 * 60  # 15 minutes

# Extra flags passed to pi via --pi-flag (validated at startup against pi --help).
# Each string may contain multiple whitespace-separated tokens.
_PI_FLAGS: list[str] = []

# ─────────────────────────────────────────────────────────
# C1 step 14a — providers.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# ProviderError, ProviderRateLimitError, ProviderQuotaError,
# _classify_provider_error, _find_alternate_agent,
# _revert_to_ready, _create_provider_issue, _sleep_with_interrupt,
# _handle_provider_error, RATE_LIMIT_BACKOFF_SECONDS, and the
# PROVIDER_*_PATTERNS lists all live at core.pipeline.providers
# (per spec §6.1, §10.3 C1). They are re-imported here so existing
# callers that ``from core.engine import ProviderError`` (or any of
# the others) continue to work. New code should import directly
# from core.pipeline.providers.
from core.pipeline.providers import (  # noqa: E402,F401
    PROVIDER_QUOTA_PATTERNS,
    PROVIDER_RATE_LIMIT_PATTERNS,
    RATE_LIMIT_BACKOFF_SECONDS,
    ProviderError,
    ProviderQuotaError,
    ProviderRateLimitError,
    _classify_provider_error,
    _create_provider_issue,
    _find_alternate_agent,
    _handle_provider_error,
    _revert_to_ready,
    _sleep_with_interrupt,
)


def _design_spec_path(issue_num: int) -> Path:
    """Return the path to the per-issue design spec for issue_num."""
    return DESIGN_SPEC_DIR / f"{issue_num}.md"


# ─────────────────────────────────────────────────────────
# Shell helpers
# ─────────────────────────────────────────────────────────


def run(
    cmd: list[str],
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run a shell command, return CompletedProcess."""
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
        timeout=timeout,
        cwd=PROJECT_ROOT,
    )
    _check_interrupt()
    return result


def gh(*args: str) -> subprocess.CompletedProcess:
    """Run `gh` command. Raises on failure."""
    return run(["gh", *args])


# ─────────────────────────────────────────────────────────
# C1 step 4 — github/comments.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# gh_comment lives at core.pipeline.github.comments (per spec §6.1,
# §10.3 C1). It is re-imported here so existing callers that
# ``from core.engine import gh_comment`` continue to work. New code
# should import directly from core.pipeline.github.comments.
from core.pipeline.github.comments import gh_comment  # noqa: E402,F401


def git(*args: str) -> subprocess.CompletedProcess:
    """Run `git` command. Raises on failure."""
    return run(["git", *args])


# ─────────────────────────────────────────────────────────
# C1 step 6 — github/client.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# _build_github_client lives at core.pipeline.github.client (per
# spec §6.1, §10.3 C1). It is re-imported here so existing callers
# that ``from core.engine import _build_github_client`` continue
# to work. New code should import directly from
# core.pipeline.github.client.
from core.pipeline.github.client import _build_github_client  # noqa: E402,F401

# ─────────────────────────────────────────────────────────
# C1 step 14b — retry.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# RetryBudget, _DEFAULT_RETRY_BUDGET, load_retry_config,
# _max_attempts_for_action, _invoke_with_retry, log_metrics,
# and _emit_trajectory all live at core.pipeline.retry (per spec
# §6.1, §10.3 C1, §10.2 B1, B4). They are re-imported here so
# existing callers that ``from core.engine import RetryBudget``
# (or any of the others) continue to work. New code should
# import directly from core.pipeline.retry.
from core.pipeline.retry import (  # noqa: E402,F401
    _DEFAULT_RETRY_BUDGET,
    RetryBudget,
    _emit_trajectory,
    _invoke_with_retry,
    _max_attempts_for_action,
    load_retry_config,
    log_metrics,
)

# ─────────────────────────────────────────────────────────
# Item 2: Ticket Fetcher
# ─────────────────────────────────────────────────────────


def fetch_ready_ticket() -> Optional[dict]:
    """
    Fetch the open status:ready issue with the smallest number.
    Checks dependencies — skips issues with unmet deps.
    Returns issue dict {number, title, body} or None.
    """
    # Get ready issues sorted by number
    result = gh(
        "issue",
        "list",
        "--label",
        "status:ready",
        "--state",
        "open",
        "--json",
        "number,title,body",
        "--limit",
        "20",
    )

    issues = json.loads(result.stdout)
    if not issues:
        return None

    # Sort by number for determinism
    issues.sort(key=lambda i: i["number"])

    for issue in issues:
        if _dependencies_met(issue):
            return issue
        else:
            print(f"[ralph] Skipping #{issue['number']} — unmet dependencies")

    return None


# Retry labels let humans re-queue a blocked issue without re-running all stages.
# Ordered smallest scope first — verify-only is faster than build+verify.
RETRY_LABEL_MAP = {
    "status:verify-retry": "verify",
    "status:build-retry": "build",
}


def fetch_retry_issue() -> Optional[tuple[dict, str]]:
    """
    Fetch the open retry-labeled issue with the smallest number.

    Checks status:verify-retry first (fastest), then status:build-retry.
    Returns (issue_dict, resume_stage) or None.
    """
    for label, resume_stage in RETRY_LABEL_MAP.items():
        try:
            result = gh(
                "issue",
                "list",
                "--label",
                label,
                "--state",
                "open",
                "--json",
                "number,title,body",
                "--limit",
                "10",
            )
            issues = json.loads(result.stdout)
            if not issues:
                continue
            issues.sort(key=lambda i: i["number"])
            for issue in issues:
                if _dependencies_met(issue):
                    return issue, resume_stage
                else:
                    print(f"[ralph] Skipping #{issue['number']} — unmet dependencies")
        except subprocess.CalledProcessError:
            continue
    return None


def sync_ready_board():
    """
    Ensure all open status:ready issues are in the Ready board column.
    This fixes the common case where an issue was added to the project in the
    default Backlog column even though it already has the status:ready label.
    """
    try:
        result = gh(
            "issue",
            "list",
            "--label",
            "status:ready",
            "--state",
            "open",
            "--json",
            "number",
            "--limit",
            "50",
        )
        issues = json.loads(result.stdout)
        for issue in issues:
            sync_status(issue["number"], "status:ready")
    except Exception as e:
        # Fail-soft: board sync must never break the pipeline.
        print(f"[ralph] WARNING: could not sync ready tickets: {e}")


def fetch_issue_by_number(issue_num: int) -> Optional[dict]:
    """Fetch a specific GitHub issue by number.

    Returns the issue dict {number, title, body, state} or None if:
    - The issue doesn't exist
    - The issue is closed
    - Dependencies are unmet
    """
    try:
        result = gh(
            "issue",
            "view",
            str(issue_num),
            "--json",
            "number,title,body,state",
        )
        issue = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None

    if issue.get("state") != "OPEN":
        return None

    if not _dependencies_met(issue):
        return None

    return issue


def _dependencies_met(issue: dict) -> bool:
    """Check if all 'Depends on: #N' references in the body are closed."""
    body = issue.get("body") or ""
    deps = _parse_depends_on(body)
    for dep_num in deps:
        try:
            result = gh(
                "issue", "view", str(dep_num), "--json", "state", "--jq", ".state"
            )
            state = result.stdout.strip()
            if state != "CLOSED":
                print(
                    f"[ralph] #{issue['number']} depends on #{dep_num} (still {state})"
                )
                return False
        except subprocess.CalledProcessError:
            print(f"[ralph] #{issue['number']} depends on #{dep_num} (not found)")
            return False
    return True


def _parse_depends_on(body: str) -> list[int]:
    """Extract issue numbers from 'Depends on: #42' patterns in the body."""
    import re

    deps = []
    for line in body.splitlines():
        match = re.search(r"Depends\s+on:\s*#(\d+)", line, re.IGNORECASE)
        if match:
            deps.append(int(match.group(1)))
    return deps


# ─────────────────────────────────────────────────────────
# Item 4: Label Management
# ─────────────────────────────────────────────────────────
# transition_label lives at core.pipeline.github.labels (per
# spec §6.1, §10.3 C1). It is re-imported here so existing
# callers that ``from core.engine import transition_label``
# continue to work. New code should import directly from
# core.pipeline.github.labels.
from core.pipeline.github.labels import transition_label  # noqa: E402,F401

# ─────────────────────────────────────────────────────────
# Item 3: Single-Stage Pipeline
# ─────────────────────────────────────────────────────────


def run_pipeline(
    issue: dict, auto_close: bool = False, resume_stage: Optional[str] = None
) -> bool:
    """
    Phase 3: 3-stage pipeline with sub-agents.
    DESIGN saves session for Mode B context inheritance.
    BUILD spawns TEST (Mode A) + IMPLEMENT (Mode B --continue) sub-agents.
    VERIFY runs as Mode A isolated sub-agent.

    Args:
        issue: The GitHub issue dict.
        auto_close: If True, close the issue on successful VERIFY
                    instead of marking status:review.
        resume_stage: If "build", skip DESIGN and start at BUILD.
                      If "verify", skip DESIGN+BUILD and start at VERIFY.
                      None runs the full pipeline from DESIGN.
    """
    issue_num = issue["number"]

    print(f"\n{'='*50}")
    print(f"[ralph] Pipeline starting for #{issue_num}: {issue['title']}")
    print(f"{'='*50}\n")

    log_metrics("pipeline_start", issue=str(issue_num), resume_stage=resume_stage or "")
    gh_comment(
        issue_num, f"⏳ Ralph pipeline started for #{issue_num}: {issue['title']}"
    )

    # ── Pre-flight check ──
    if PREFLIGHT_SCRIPT.exists():
        result = run(["bash", str(PREFLIGHT_SCRIPT)], check=False)
        if result.returncode != 0:
            print(f"[ralph] Pre-flight FAILED for #{issue_num}")
            gh_comment(issue_num, "🚦 Pre-flight checks failed. Blocking issue.")
            transition_label(issue_num, "status:blocked", "status:design")
            return False

    # ── STAGE 1: DESIGN ──
    if resume_stage in ("build", "verify"):
        gh_comment(
            issue_num,
            f"⏭️ Skipping DESIGN — resuming from `{resume_stage}`. "
            "Using existing design spec.",
        )
    else:
        save_checkpoint(issue_num, "design")
        try:
            design_ok = run_design_stage(issue)
        except ProviderError:
            clear_checkpoint()
            raise
        if not design_ok:
            clear_checkpoint()
            _cleanup_issue_artifacts(issue_num)
            partial_spec = _read_partial_design_spec(issue_num)
            detail = _format_stage_failure("DESIGN", partial_spec=partial_spec)
            gh_comment(issue_num, detail)
            transition_label(issue_num, "status:blocked", "status:design")
            log_metrics(
                "pipeline_complete",
                issue=str(issue_num),
                result="blocked",
                stage="design",
            )
            return False
        try:
            commit_stage(issue_num, "design")
        except subprocess.CalledProcessError:
            clear_checkpoint()
            _cleanup_issue_artifacts(issue_num)
            gh_comment(issue_num, "💥 DESIGN commit/push failed. Blocking issue.")
            transition_label(issue_num, "status:blocked", "status:design")
            log_metrics(
                "pipeline_complete",
                issue=str(issue_num),
                result="blocked",
                stage="design",
                reason="push_failed",
            )
            return False
        gh_comment(issue_num, "✅ DESIGN stage completed and committed.")
        # Post a permanent design summary to the GitHub issue.
        design_summary = _summarize_design_spec(issue_num)
        if design_summary:
            gh_comment(issue_num, design_summary)
        transition_label(issue_num, "status:build", "status:design")

    # ── STAGE 2: BUILD ──
    if resume_stage == "verify":
        gh_comment(
            issue_num,
            "⏭️ Skipping BUILD — resuming from `verify`. "
            "Using existing implementation.",
        )
    else:
        save_checkpoint(issue_num, "build")
        try:
            build_ok = run_build_stage(issue)
        except ProviderError:
            clear_checkpoint()
            raise
        if not build_ok:
            clear_checkpoint()
            _archive_issue_artifacts(issue_num)
            # run_build_stage already posted a detailed failure comment.
            # Post a summary pointer to the archived report.
            report_file = PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-report.md"
            if report_file.exists():
                gh_comment(
                    issue_num,
                    f"📋 Full failure report saved to "
                    f"`.ralph/blocked/issue-{issue_num}/issue-{issue_num}-report.md` "
                    f"(also visible in `.ralph/issue-{issue_num}-report.md`).",
                )
            transition_label(issue_num, "status:blocked", "status:build")
            log_metrics(
                "pipeline_complete",
                issue=str(issue_num),
                result="blocked",
                stage="build",
            )
            return False
        try:
            commit_stage(issue_num, "build")
        except subprocess.CalledProcessError:
            clear_checkpoint()
            _cleanup_issue_artifacts(issue_num)
            gh_comment(issue_num, "💥 BUILD commit/push failed. Blocking issue.")
            transition_label(issue_num, "status:blocked", "status:build")
            log_metrics(
                "pipeline_complete",
                issue=str(issue_num),
                result="blocked",
                stage="build",
                reason="push_failed",
            )
            return False
        gh_comment(issue_num, "✅ BUILD stage completed and committed.")
        transition_label(issue_num, "status:verify", "status:build")

    # ── STAGE 3: VERIFY ──
    save_checkpoint(issue_num, "verify")
    try:
        verify_pass = run_verify_stage(issue)
    except ProviderError:
        clear_checkpoint()
        raise
    clear_checkpoint()
    _cleanup_issue_artifacts(issue_num)

    if verify_pass:
        print(f"\n[ralph] #{issue_num} PASSED — handing off for review")
        if auto_close:
            sync_closed(issue_num)
            gh_comment(issue_num, "✅ VERIFY passed. Auto-closing issue.")
            gh("issue", "close", str(issue_num))
            print(f"[ralph] #{issue_num} auto-closed")
            log_metrics("pipeline_complete", issue=str(issue_num), result="closed")
        else:
            gh_comment(
                issue_num,
                "✅ VERIFY passed. Handing off for review — external tools and reviewers may now update labels on this issue. Ralph will not touch this issue again unless a retry label is set.",
            )
            transition_label(issue_num, "status:review", "status:verify")
            transition_label(issue_num, "status:review", "status:verify")
            log_metrics("pipeline_complete", issue=str(issue_num), result="review")
    else:
        print(f"\n[ralph] #{issue_num} FAILED VERIFY — marking blocked")
        _archive_issue_artifacts(issue_num)
        # run_verify_stage already posts review result; add a pointer to the report
        report_file = PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-report.md"
        if report_file.exists():
            gh_comment(
                issue_num,
                f"📋 Full VERIFY failure report at "
                f"`.ralph/blocked/issue-{issue_num}/issue-{issue_num}-report.md`.",
            )
        transition_label(issue_num, "status:blocked", "status:verify")
        transition_label(issue_num, "status:blocked", "status:verify")
        log_metrics(
            "pipeline_complete", issue=str(issue_num), result="blocked", stage="verify"
        )

    return verify_pass


# ─────────────────────────────────────────────────────────
# Stage runners
# ─────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────
# C1 step 10 — stages/design.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# run_design_stage lives at core.pipeline.stages.design (per spec
# §6.1, §10.3 C1). It is re-imported here so existing callers that
# ``from core.engine import run_design_stage`` continue to work.
# New code should import directly from core.pipeline.stages.design.
from core.pipeline.stages.design import run_design_stage  # noqa: E402,F401


def run_build_stage(issue: dict) -> bool:
    """
    STAGE 2: BUILD — spawns two sub-agents:
      1. TEST sub-agent (Mode A — isolated, fresh session)
      2. IMPLEMENT sub-agent (Mode B — full context)
    Sequential: TEST runs first (writes tests), then IMPLEMENT (writes code).
    """
    issue_num = issue["number"]
    print(f"\n[ralph] STAGE 2/3: BUILD for #{issue_num}")
    gh_comment(issue_num, "🔨 BUILD stage started.")
    log_metrics("stage_start", issue=str(issue_num), stage="build")

    # Run pre-flight before build
    if PREFLIGHT_SCRIPT.exists():
        result = run(["bash", str(PREFLIGHT_SCRIPT)], check=False)
        if result.returncode != 0:
            print(f"[ralph] Pre-flight FAILED for #{issue_num}")
            gh_comment(issue_num, "🚦 BUILD pre-flight checks failed. Blocking issue.")
            return False

    # ── Step 2a: TEST sub-agent (Mode A — isolated) ──
    if not _run_test_subagent(issue):
        _write_stage_report(
            issue_num,
            "BUILD",
            "TEST sub-agent",
            "TEST sub-agent (Mode A) failed to write tests.",
        )
        _rollback_working_tree()
        log_metrics("stage_complete", issue=str(issue_num), stage="build")
        return False

    # ── Step 2b: IMPLEMENT sub-agent (Mode B — full context) ──
    # Snapshot QA test files before IMPLEMENT to detect tampering.
    qa_test_paths_before = _load_test_tracking(issue_num)
    qa_test_paths_before = [
        t for t in qa_test_paths_before if t.endswith(".py") and "__pycache__" not in t
    ]
    qa_test_paths_before = _resolve_existing_test_paths(qa_test_paths_before)

    if not _run_implement_subagent(issue):
        _write_stage_report(
            issue_num,
            "BUILD",
            "IMPLEMENT sub-agent",
            "IMPLEMENT sub-agent (Mode B) failed to implement code.",
        )
        _rollback_working_tree()
        log_metrics("stage_complete", issue=str(issue_num), stage="build")
        return False

    # A2.2 sanity check: every QA-written test file must still be mode 0o444.
    # Raises TamperedTestsError if any file is unlocked or missing.
    try:
        _detect_tampered_tests(qa_test_paths_before)
    except TamperedTestsError as e:
        # Hard block per spec §10.1 A2: tampering is no longer advisory.
        _write_stage_report(
            issue_num,
            "BUILD",
            "tampering detected",
            str(e),
        )
        gh_comment(
            issue_num,
            f"🚫 IMPLEMENT sub-agent tampered with QA-written test files: {e}. "
            "Build blocked. Manual operator review required.",
        )
        log_metrics(
            "stage_complete", issue=str(issue_num), stage="build", result="tampering"
        )
        return False

    # ── Validation gate (only tests written by the independent QA session) ──
    print("\n[ralph] Running validation gate...")
    core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parent))
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
        print("[ralph] No QA-written tests detected; falling back to targeted tier")
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
        gh_comment(issue_num, "✅ BUILD validation gate passed.")
    else:
        gh_comment(issue_num, "❌ BUILD validation gate failed.")
        # Capture the full output for the report
        val_output = (val_result.stdout or "") + "\n" + (val_result.stderr or "")
        # Echo to terminal so the operator can see it live too
        if val_result.stdout:
            print(val_result.stdout, end="")
        if val_result.stderr:
            print(val_result.stderr, end="", file=sys.stderr)
        # Extract the key failure lines for the GitHub comment
        failure_summary = _extract_failure_summary(
            val_result.stdout or "", val_result.stderr or ""
        )
        _write_stage_report(
            issue_num,
            "BUILD",
            "VALIDATION gate",
            val_output.strip() or "(no output captured)",
        )
        # Post the failure summary immediately so the issue shows what broke
        detail = _format_stage_failure(
            "BUILD",
            report_content=f"**QA tests:** {', '.join(qa_tests) if qa_tests else 'targeted tier'}\n\n{failure_summary}",
        )
        gh_comment(issue_num, detail)
        _rollback_working_tree()

    log_metrics("stage_complete", issue=str(issue_num), stage="build")
    return success


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
    from core.pipeline.agents.base import create_worktree, remove_worktree

    print(f"\n[ralph] STAGE 3/3: VERIFY for #{issue_num}")
    gh_comment(issue_num, "🔍 VERIFY stage started (independent review).")
    log_metrics(
        "stage_start", issue=str(issue_num), stage="verify", subagent="verify", mode="A"
    )

    wt_path: Optional[Path] = None
    try:
        wt_path = create_worktree(issue_num)
    except RuntimeError as e:
        print(f"[ralph] WARNING: worktree unavailable, running in repo root: {e}")

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
            core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parent))
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


# ─────────────────────────────────────────────────────────
# Sub-Agent Methods (Phase 3)
# ─────────────────────────────────────────────────────────


def _run_test_subagent(issue: dict) -> bool:
    """
    TEST sub-agent — Mode A (isolated, fresh session).
    Sees design spec ONLY. Writes tests that SHOULD FAIL.
    No implementation code visibility.
    Snapshots tests/ before and after so VERIFY can run only these QA-written tests.

    Per spec §10.2 B3, the agent runs inside a git worktree so it
    cannot corrupt the parent repo. ``create_worktree`` runs first;
    ``remove_worktree`` runs in a finally block to survive failures.
    """
    issue_num = issue["number"]
    from core.pipeline.agents.base import create_worktree, remove_worktree

    print(f"\n  [ralph] BUILD / TEST sub-agent for #{issue_num} (Mode A — isolated)")
    gh_comment(issue_num, "🧪 TEST sub-agent started (isolated).")
    log_metrics("subagent_start", issue=str(issue_num), subagent="test", mode="A")

    wt_path: Optional[Path] = None
    try:
        wt_path = create_worktree(issue_num)
    except RuntimeError as e:
        # Worktree unavailable (e.g., git too old). Fall back to running
        # in the repo root — operators get a clear error message in logs.
        print(f"[ralph] WARNING: worktree unavailable, running in repo root: {e}")

    try:
        before_tests = _snapshot_tests_dir()
        prompt = _assemble_subagent_prompt(issue, "test.md", mode="A")
        success = invoke_agent(prompt, issue_num)
        after_tests = _snapshot_tests_dir()
        new_tests = _detect_new_tests(before_tests, after_tests)
        _save_test_tracking(issue_num, new_tests)
        if new_tests:
            print(f"  [ralph] TEST stage created/modified tests: {new_tests}")
            gh_comment(
                issue_num,
                f"🧪 TEST stage produced {len(new_tests)} test file(s): "
                f"{', '.join(new_tests)}",
            )

        if success:
            # A2.1: hard-block test tampering — chmod the QA-written test files
            # to 0o444 so the IMPLEMENT sub-agent cannot modify them. Idempotent.
            if new_tests:
                for rel_path in new_tests:
                    abs_path = (
                        PROJECT_ROOT / rel_path
                        if not Path(rel_path).is_absolute()
                        else Path(rel_path)
                    )
                    if abs_path.exists():
                        try:
                            os.chmod(abs_path, 0o444)
                            print(f"[ralph] Locked QA test: {rel_path} (mode 0o444)")
                        except OSError as e:
                            print(f"[ralph] WARNING: failed to chmod {rel_path}: {e}")
            gh_comment(issue_num, "✅ TEST sub-agent completed.")
        else:
            gh_comment(
                issue_num,
                "❌ TEST sub-agent failed (non-zero exit). "
                "Check daemon logs for the agent conversation output.",
            )
        log_metrics(
            "subagent_complete",
            issue=str(issue_num),
            subagent="test",
            mode="A",
            result="success" if success else "failure",
            test_count=len(new_tests) if new_tests else 0,
        )
        return success
    finally:
        if wt_path is not None:
            remove_worktree(wt_path)


def _run_implement_subagent(issue: dict) -> bool:
    """
    IMPLEMENT sub-agent — Mode B (true context inheritance via --continue).
    Continues the DESIGN session, inheriting full codebase knowledge.
    Finds test files on disk and implements code to make them pass.
    """
    issue_num = issue["number"]
    print(
        f"\n  [ralph] BUILD / IMPLEMENT sub-agent for #{issue_num} (Mode B — inherits DESIGN context)"
    )
    gh_comment(issue_num, "🛠️ IMPLEMENT sub-agent started (continuing DESIGN context).")
    log_metrics("subagent_start", issue=str(issue_num), subagent="implement", mode="B")

    session_file = PROJECT_ROOT / ".ralph" / f"session-{issue_num}.jsonl"
    prompt = _assemble_subagent_prompt(issue, "implement.md", mode="B")

    # Inject the exact list of QA-written test files so the agent knows
    # precisely which tests it must pass — not just the TEST_MAP-based
    # set produced by `ralph validate --tier=targeted`.
    qa_tests = _load_test_tracking(issue_num)
    qa_tests = [t for t in qa_tests if t.endswith(".py") and "__pycache__" not in t]
    qa_tests = _resolve_existing_test_paths(qa_tests)
    if qa_tests:
        test_list = "\n".join(f"  - {t}" for t in qa_tests)
        prompt += (
            f"\n\n## QA-Written Test Files (must pass)\n\n"
            f"These test files were written by the independent QA sub-agent. "
            f"You MUST run these specific tests and ensure they pass:\n\n"
            f"{test_list}\n\n"
            f"Run them with:\n"
            f"  ralph validate --tier=targeted --pytest-paths {' '.join(qa_tests)}\n"
        )

    success = invoke_agent(
        prompt, issue_num, session_file=session_file, continue_session=True
    )

    if success:
        gh_comment(issue_num, "✅ IMPLEMENT sub-agent completed.")
    else:
        gh_comment(
            issue_num,
            "❌ IMPLEMENT sub-agent failed (non-zero exit). "
            "Check daemon logs for the agent conversation output.",
        )
    log_metrics(
        "subagent_complete",
        issue=str(issue_num),
        subagent="implement",
        mode="B",
        result="success" if success else "failure",
    )
    return success


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


def _rollback_working_tree():
    """Discard all uncommitted changes so stale files don't pollute later stages.

    Uses the checkpoint's pre_stage_sha for a precise rollback to the exact
    state before the BUILD stage started. This avoids two problems with the
    old approach (git clean -fd + git checkout -- .):

    1. git clean -fd destroys entire untracked directories (e.g. a new
       adapters/ subpackage created by the IMPLEMENT agent). On retry the
       agent may not recreate them, causing "missing __init__.py" lint errors.

    2. git checkout -- . resets to the index, not HEAD. If stray staged
       changes exist, the restore is imprecise.
    """
    try:
        # Read pre_stage_sha from checkpoint for precise rollback
        pre_sha = None
        if CHECKPOINT_FILE.exists():
            try:
                data = json.loads(CHECKPOINT_FILE.read_text())
                pre_sha = data.get("pre_stage_sha")
            except Exception:
                pass

        if pre_sha:
            # Reset tracked files + index to pre-build state
            run(["git", "reset", "--hard", pre_sha], check=False, capture=True)
            # Remove untracked files and directories
            run(["git", "clean", "-fd"], check=False, capture=True)
            print(
                f"[ralph] Working tree rolled back to checkpoint " f"SHA {pre_sha[:8]}."
            )
        else:
            # Fallback: restore tracked files to HEAD
            run(["git", "clean", "-fd"], check=False, capture=True)
            run(["git", "checkout", "--", "."], check=False, capture=True)
            print("[ralph] Working tree rolled back after BUILD failure (fallback).")
    except Exception as e:
        print(f"[ralph] WARNING: rollback failed: {e}")


def _file_hash(path: Path) -> str:
    """Return SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot_tests_dir() -> dict[str, str]:
    """Return {relative_path: content_hash} for all .py files under tests/.

    Excludes __pycache__/, .pytest_cache/, and non-.py files so that
    transient cache artifacts don't leak into the test tracking manifest.
    """
    tests_dir = PROJECT_ROOT / "tests"
    snapshot: dict[str, str] = {}
    if tests_dir.exists():
        for p in tests_dir.rglob("*"):
            if not p.is_file():
                continue
            # Exclude cache directories and non-.py files
            if any(part in ("__pycache__", ".pytest_cache") for part in p.parts):
                continue
            if p.suffix != ".py":
                continue
            snapshot[str(p.relative_to(PROJECT_ROOT))] = _file_hash(p)
    return snapshot


def _detect_new_tests(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Return paths that are new or modified between two test snapshots.

    Only includes .py files; filters out cache artifacts defensively.
    """
    return sorted(
        path
        for path, digest in after.items()
        if path not in before or before[path] != digest
        if path.endswith(".py")
    )


def _snapshot_file_hashes(paths: list[str]) -> dict[str, str]:
    """Return {relative_path: content_hash} for an explicit list of file paths.

    Paths that don't exist on disk are silently skipped.
    """
    snapshot: dict[str, str] = {}
    for p in paths:
        full = PROJECT_ROOT / p
        if full.is_file():
            snapshot[p] = _file_hash(full)
    return snapshot


def _detect_tampered_tests(test_paths: list[str]) -> bool:
    """Sanity check: every QA-written test file must have mode 0o444.

    Per spec §10.1 A2 (A2.2): the A2.1 chmod at the end of TEST stage makes
    content tampering impossible at the filesystem level. This function is a
    sanity check that the chmod is still in place after the IMPLEMENT stage.

    Returns True if all files have mode 0o444.
    Raises TamperedTestsError if any file has mode != 0o444 (or has been
    deleted/relocated), and logs at ERROR level.

    Note: signature changed from v3 (was content-hash based). The new
    mechanism-enforced check is cheaper and stronger.
    """
    tampered: list[str] = []
    for path_str in test_paths:
        full = (
            PROJECT_ROOT / path_str
            if not Path(path_str).is_absolute()
            else Path(path_str)
        )
        if not full.exists():
            tampered.append(path_str)
            continue
        mode = full.stat().st_mode & 0o777
        if mode != 0o444:
            tampered.append(path_str)

    if tampered:
        logging.error(
            "[ralph] TAMPERING DETECTED: %d QA test file(s) are not locked (mode != 0o444): %s",
            len(tampered),
            tampered,
        )
        raise TamperedTestsError(
            f"QA test file(s) not in locked state (mode != 0o444): {tampered}"
        )

    return True


class TamperedTestsError(Exception):
    """Raised when QA-written test files are no longer in the locked state.

    Per spec §10.1 A2 — the IMPLEMENT sub-agent must not be able to modify
    test files that the TEST sub-agent wrote. A2.1 enforces this with a
    chmod 0o444 lock; A2.2 detects any escape via this exception.
    """

    pass


def _test_tracking_file(issue_num: int) -> Path:
    return PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-tests.json"


def _save_test_tracking(issue_num: int, test_paths: list[str]):
    """Persist the list of test files created during the TEST stage.

    Sanitizes input to exclude cache artifacts (__pycache__/, .pytest_cache/)
    and non-.py files. The agent's output is untrusted input.
    """
    sanitized = [
        p
        for p in test_paths
        if p.endswith(".py") and "__pycache__" not in p and ".pytest_cache" not in p
    ]
    path = _test_tracking_file(issue_num)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tests": sanitized}, indent=2))


def _load_test_tracking(issue_num: int) -> list[str]:
    """Load the list of test files created during the TEST stage."""
    path = _test_tracking_file(issue_num)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("tests", [])
    except Exception:
        return []


def _resolve_existing_test_paths(test_paths: list[str]) -> list[str]:
    """Filter test_paths to only those that exist on disk under PROJECT_ROOT.

    Logs a warning for any path that is missing so the operator knows a
    tracked test file has been deleted or renamed.
    """
    existing: list[str] = []
    for p in test_paths:
        full = PROJECT_ROOT / p
        if full.is_file():
            existing.append(p)
        else:
            print(f"[ralph] WARNING: tracked test file not found: {p}")
    return existing


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


def _archived_issue_dir(issue_num: int) -> Path:
    """Return the archive directory for a blocked issue's artifacts."""
    return PROJECT_ROOT / ".ralph" / "blocked" / f"issue-{issue_num}"


def _cleanup_issue_artifacts(issue_num: int):
    """Remove session and per-issue test-tracking files after pipeline SUCCEEDS.

    On failure, artifacts are MOVED to .ralph/blocked/issue-N/ instead of
    being deleted, so a human can inspect the evidence.
    """
    session_file = PROJECT_ROOT / ".ralph" / f"session-{issue_num}.jsonl"
    if session_file.exists():
        session_file.unlink()
        print(f"[ralph] Cleaned up session: {session_file.name}")

    tracking_file = _test_tracking_file(issue_num)
    if tracking_file.exists():
        tracking_file.unlink()
        print(f"[ralph] Cleaned up test tracking: {tracking_file.name}")


def _archive_issue_artifacts(issue_num: int):
    """Move session and test-tracking files to .ralph/blocked/ for inspection."""
    archive_dir = _archived_issue_dir(issue_num)
    archive_dir.mkdir(parents=True, exist_ok=True)

    session_file = PROJECT_ROOT / ".ralph" / f"session-{issue_num}.jsonl"
    if session_file.exists():
        dest = archive_dir / session_file.name
        session_file.rename(dest)
        print(f"[ralph] Archived session: {session_file.name} → blocked/")

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


def _has_commits() -> bool:
    """Check if the repo has any commits (vs. fresh repo)."""
    try:
        result = git("rev-list", "--count", "HEAD")
        return int(result.stdout.strip()) >= 2
    except Exception:
        return False


def _has_unpushed_commits(branch: str) -> bool:
    """Return True if the local branch has commits not yet pushed to origin."""
    try:
        result = git("rev-list", "--count", f"origin/{branch}..{branch}")
        return int(result.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        # No upstream or origin branch missing — assume nothing to push.
        return False


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

    Mode B (Context inherit): issue body + reference docs + stage persona + recent comments.
      Session context is inherited via pi --continue.
      Design spec is already in the session — no need to re-inject.
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
        else "Sub-Agent Instructions (Mode B — continuing DESIGN session)"
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
            "**CONTEXT NOTE:** You are a Mode B sub-agent continuing from the DESIGN session. "
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


def commit_stage(issue_num: int, stage: str):
    """Commit all changes after a pipeline stage completes and push to origin."""
    msg = f"[ralph] {stage}: #{issue_num}"
    committed = False
    try:
        git("add", "-A")
        git("commit", "-m", msg)
        print(f"[ralph] Committed: {msg}")
        committed = True
    except subprocess.CalledProcessError:
        # No changes to commit (e.g., DESIGN stage may not change files)
        print(f"[ralph] Nothing to commit for {stage}")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if _has_unpushed_commits(branch):
        _push_with_retry(branch)
    elif committed:
        print(f"[ralph] No unpushed commits on {branch}")


def _push_with_retry(branch: str, retries: int = 3, backoff: float = 2.0):
    """Push current branch to origin with retries. Raises on final failure."""
    for attempt in range(1, retries + 1):
        try:
            git("push", "-u", "origin", branch)
            print(f"[ralph] Pushed to origin/{branch}")
            return
        except subprocess.CalledProcessError as e:
            if attempt < retries:
                wait = backoff**attempt
                print(
                    f"[ralph] Push failed (attempt {attempt}/{retries}), "
                    f"retrying in {wait:.0f}s..."
                )
                _check_interrupt()
                time.sleep(wait)
            else:
                print(
                    f"[ralph] ERROR: Push to origin/{branch} failed after "
                    f"{retries} attempts: {e}"
                )
                raise


def _parse_reference_docs(body: str) -> list[str]:
    """Extract 'Reference: path/to/doc.md' from issue body."""
    import re

    refs = []
    for line in body.splitlines():
        match = re.search(r"Reference:\s*(\S+)", line, re.IGNORECASE)
        if match:
            refs.append(match.group(1))
    return refs


# ─────────────────────────────────────────────────────────
# C1 step 8 — agents/pi.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# invoke_agent, invoke_agent_with_output, _resolve_agent_binary,
# _get_kimi_session_id, _parse_pi_valid_flags, validate_pi_flags,
# and the per-cmd _PI_FLAGS list all live at core.pipeline.agents.pi
# (per spec §6.1, §10.3 C1). They are re-imported here so existing
# callers that ``from core.engine import invoke_agent`` (or any of
# the others) continue to work. New code should import directly
# from core.pipeline.agents.pi.
from core.pipeline.agents.pi import (  # noqa: E402,F401
    _PI_FLAGS,
    _get_kimi_session_id,
    _parse_pi_valid_flags,
    _resolve_agent_binary,
    invoke_agent,
    invoke_agent_with_output,
    validate_pi_flags,
)

# ─────────────────────────────────────────────────────────
# C1 step 2 — checkpoint.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# save_checkpoint and clear_checkpoint live at core.pipeline.checkpoint
# (per spec §6.1, §10.3 C1). They are re-imported here so existing
# callers that ``from core.engine import save_checkpoint`` continue
# to work. New code should import directly from core.pipeline.checkpoint.
from core.pipeline.checkpoint import clear_checkpoint  # noqa: E402,F401
from core.pipeline.checkpoint import save_checkpoint  # noqa: E402,F401

# ─────────────────────────────────────────────────────────
# C1 step 3 — recovery.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# recover_from_crash, the daemon signal-handling machinery
# (RalphInterrupted, _handle_signal, _check_interrupt), the
# _shutdown_requested / _in_cleanup module state, and the PID file
# management helpers (acquire_pid_file, release_pid_file) all
# live at core.pipeline.recovery (per spec §6.1, §10.3 C1). They
# are re-imported here so existing callers that ``from core.engine
# import recover_from_crash`` (or any of the others) continue to
# work. New code should import directly from core.pipeline.recovery.
from core.pipeline.recovery import RalphInterrupted  # noqa: E402,F401
from core.pipeline.recovery import (  # noqa: E402,F401
    _check_interrupt,
    _handle_signal,
    _in_cleanup,
    _shutdown_requested,
    acquire_pid_file,
    recover_from_crash,
    release_pid_file,
)

# ─────────────────────────────────────────────────────────
# Item 7: Checkpoint & Crash Recovery
# ─────────────────────────────────────────────────────────


def run_loop(auto_close: bool = False, single_issue: Optional[int] = None):
    """
    The daemon loop. Runs until interrupted.

    Args:
        auto_close: If True, close issues on success instead of
                    marking status:review.
        single_issue: If set, process only this issue number and exit.
    """
    if not acquire_pid_file():
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print("[ralph] Daemon started")
    log_metrics("daemon_start")

    try:
        recovered = recover_from_crash()
        tried_agents: set[str] = set()

        while not _shutdown_requested:
            # ── Sync ──
            print("[ralph] Syncing with remote...")
            try:
                git("fetch", "origin")
                branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
                upstream = f"origin/{branch}"
                git("merge", upstream, "--ff-only")
            except subprocess.CalledProcessError:
                print("[ralph] Warning: git sync failed — continuing with local state")

            # ── Single-issue mode (--issue=N) ──
            if single_issue is not None:
                print(f"[ralph] Single-issue mode: processing only #{single_issue}")
                issue = fetch_issue_by_number(single_issue)
                if issue is None:
                    print(
                        f"[ralph] Issue #{single_issue} not found, closed, "
                        "or has unmet dependencies."
                    )
                    log_metrics(
                        "pipeline_complete",
                        issue=str(single_issue),
                        result="skipped",
                        reason="not_found_or_closed",
                    )
                    break
                transition_label(single_issue, "status:design", "status:ready")
                gh_comment(
                    single_issue,
                    f"⏳ Ralph claimed #{single_issue} and started DESIGN (single-issue mode).",
                )
                try:
                    run_pipeline(issue, auto_close=auto_close)
                except ProviderError as e:
                    if _handle_provider_error(issue, e, tried_agents) == "break":
                        break
                    continue
                break

            # ── Handle crash recovery resume ──
            if recovered:
                issue = recovered["issue"]
                resume_stage = recovered["resume_stage"]
                issue_num = issue["number"]
                print(f"[ralph] Resuming #{issue_num} from stage: {resume_stage}")

                if resume_stage == "build":
                    gh_comment(
                        issue_num, "🔄 Ralph resuming BUILD stage after crash recovery."
                    )
                    save_checkpoint(issue_num, "build")
                    try:
                        success = run_build_stage(issue)
                    except ProviderError as e:
                        if _handle_provider_error(issue, e, tried_agents) == "break":
                            break
                        recovered = None
                        continue
                    if not success:
                        gh_comment(
                            issue_num, "❌ Resumed BUILD stage failed. Blocking issue."
                        )
                        transition_label(issue_num, "status:blocked", "status:build")
                        clear_checkpoint()
                        recovered = None
                        continue
                    try:
                        commit_stage(issue_num, "build")
                    except subprocess.CalledProcessError:
                        clear_checkpoint()
                        gh_comment(
                            issue_num,
                            "💥 Resumed BUILD commit/push failed. Blocking issue.",
                        )
                        transition_label(issue_num, "status:blocked", "status:build")
                        log_metrics(
                            "pipeline_complete",
                            issue=str(issue_num),
                            result="blocked",
                            stage="build",
                            reason="push_failed",
                        )
                        recovered = None
                        continue
                    gh_comment(
                        issue_num, "✅ Resumed BUILD stage completed and committed."
                    )
                    transition_label(issue_num, "status:verify", "status:build")
                    # Fall through to VERIFY
                    resume_stage = "verify"

                if resume_stage == "verify":
                    gh_comment(
                        issue_num,
                        "🔄 Ralph resuming VERIFY stage after crash recovery.",
                    )
                    save_checkpoint(issue_num, "verify")
                    try:
                        verify_pass = run_verify_stage(issue)
                    except ProviderError as e:
                        if _handle_provider_error(issue, e, tried_agents) == "break":
                            break
                        recovered = None
                        continue
                    clear_checkpoint()
                    if verify_pass:
                        if auto_close:
                            sync_closed(issue_num)
                            gh_comment(
                                issue_num,
                                "✅ Resumed VERIFY passed. Auto-closing issue.",
                            )
                            gh("issue", "close", str(issue_num))
                            print(f"[ralph] #{issue_num} auto-closed")
                            log_metrics(
                                "pipeline_complete",
                                issue=str(issue_num),
                                result="closed",
                            )
                        else:
                            gh_comment(
                                issue_num,
                                "✅ Resumed VERIFY passed. Handing off for review — external tools and reviewers may now update labels on this issue. Ralph will not touch this issue again unless a retry label is set.",
                            )
                            transition_label(
                                issue_num, "status:review", "status:verify"
                            )
                            log_metrics(
                                "pipeline_complete",
                                issue=str(issue_num),
                                result="review",
                            )
                    else:
                        gh_comment(
                            issue_num, "❌ Resumed VERIFY stage failed. Blocking issue."
                        )
                        transition_label(issue_num, "status:blocked", "status:verify")
                        log_metrics(
                            "pipeline_complete", issue=str(issue_num), result="blocked"
                        )
                    recovered = None
                    continue

                if resume_stage == "design":
                    # Run the full pipeline from scratch (already rolled back to pre-design)
                    recovered = None
                    try:
                        run_pipeline(issue, auto_close=auto_close)
                    except ProviderError as e:
                        if _handle_provider_error(issue, e, tried_agents) == "break":
                            break
                        continue
                    continue

                recovered = None
                continue

            # ── Check retry labels first (smallest scope = fastest) ──
            retry = fetch_retry_issue()
            if retry is not None:
                issue, resume_stage = retry
                tried_agents.clear()
                issue_num = issue["number"]
                if resume_stage == "verify":
                    transition_label(issue_num, "status:verify", "status:verify-retry")
                    gh_comment(
                        issue_num,
                        f"🔄 Ralph claimed #{issue_num} for VERIFY retry "
                        "(skipping DESIGN + BUILD).",
                    )
                else:
                    transition_label(issue_num, "status:build", "status:build-retry")
                    gh_comment(
                        issue_num,
                        f"🔄 Ralph claimed #{issue_num} for BUILD retry "
                        "(skipping DESIGN).",
                    )
                try:
                    run_pipeline(
                        issue, auto_close=auto_close, resume_stage=resume_stage
                    )
                except ProviderError as e:
                    if _handle_provider_error(issue, e, tried_agents) == "break":
                        break
                    continue
                if not _shutdown_requested:
                    time.sleep(5)
                continue

            # ── Ensure ready tickets are visible on the board ──
            sync_ready_board()

            # ── Fetch next ready ticket ──
            issue = fetch_ready_ticket()
            if issue is None:
                print("[ralph] No ready or retry tickets. Sleeping...")
                log_metrics("daemon_idle")
                for _ in range(60):
                    if _shutdown_requested:
                        break
                    time.sleep(1)
                continue

            # ── Claim & Pipeline ──
            tried_agents.clear()
            issue_num = issue["number"]
            transition_label(issue_num, "status:design", "status:ready")
            gh_comment(
                issue_num, f"⏳ Ralph claimed issue #{issue_num} and started DESIGN."
            )
            try:
                run_pipeline(issue, auto_close=auto_close)
            except ProviderError as e:
                if _handle_provider_error(issue, e, tried_agents) == "break":
                    break
                continue

            # Brief pause between issues
            if not _shutdown_requested:
                time.sleep(5)

    except RalphInterrupted:
        # Graceful shutdown requested; let finally mark the in-flight issue.
        pass
    except Exception as e:
        print(f"[ralph] Unhandled error: {e}")
        log_metrics("daemon_error", error=str(e))
        raise
    finally:
        global _in_cleanup
        _in_cleanup = True
        # On interrupt (SIGINT/SIGTERM), mark in-flight issue as blocked
        # and remove the active stage label so the Kanban board stays clean.
        if CHECKPOINT_FILE.exists():
            try:
                data = json.loads(CHECKPOINT_FILE.read_text())
                issue_num = data["issue"]
                stage = data.get("stage", "design")
                stage_label_map = {
                    "design": "status:design",
                    "build": "status:build",
                    "verify": "status:verify",
                }
                remove_label = stage_label_map.get(stage, "status:design")
                # Add note that the issue was interrupted
                if stage == "verify":
                    retry_hint = (
                        " Set `status:verify-retry` to re-run VERIFY only, "
                        "or `status:ready` for full pipeline."
                    )
                elif stage == "build":
                    retry_hint = (
                        " Set `status:build-retry` to re-run BUILD+VERIFY, "
                        "or `status:ready` for full pipeline."
                    )
                else:
                    retry_hint = " Set `status:ready` to retry the full pipeline."
                gh_comment(
                    issue_num,
                    "⏸️ Ralph daemon interrupted (SIGINT/SIGTERM). Issue was in "
                    f"{stage} stage.{retry_hint}",
                )
                transition_label(issue_num, "status:blocked", remove_label)
                clear_checkpoint()
                print(
                    f"[ralph] Marked #{issue_num} as status:blocked (interrupted, was: {stage})"
                )
            except Exception as e:
                print(f"[ralph] Error marking interrupted issue: {e}")
                clear_checkpoint()
        release_pid_file()
        log_metrics("daemon_stop")
        print("[ralph] Daemon stopped")
        _in_cleanup = False


# ─────────────────────────────────────────────────────────
# CLI entry point for direct invocation (ralph daemon calls this)
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Subcommand dispatch (per plan §1.1 A-prelude): `python -m core.engine migrate`
    # delegates to `core.migrate.main`. The default subcommand (no argv[1] or
    # unknown subcommand) is the existing daemon entry point.
    import argparse

    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        from core.migrate import main as migrate_main

        sys.exit(migrate_main(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="Ralph v3 Daemon")
    parser.add_argument(
        "--auto-close",
        action="store_true",
        help="Close issues on success instead of marking status:review",
    )
    parser.add_argument(
        "--agent",
        choices=["pi", "kimi"],
        default=None,
        help="AI agent to use (overrides RALPH_AGENT and config)",
    )
    parser.add_argument(
        "--issue",
        type=int,
        default=None,
        metavar="N",
        help="Process only issue #N and exit",
    )
    parser.add_argument(
        "--pi-flag",
        action="append",
        default=[],
        metavar="FLAG",
        help="Extra flag for every pi invocation (repeatable). "
        "Example: --pi-flag='--model=claude-sonnet-4' --pi-flag='--thinking high'",
    )
    args = parser.parse_args()
    if args.agent:
        os.environ["RALPH_AGENT"] = args.agent
    # Validate and store pi flags
    if args.pi_flag:
        resolved_agent = args.agent or os.environ.get("RALPH_AGENT", "") or "pi"
        if resolved_agent != "pi":
            print(
                f"[ralph] WARNING: --pi-flag is set but agent is '{resolved_agent}' (not 'pi'). Flags will be ignored."
            )
        else:
            _PI_FLAGS[:] = validate_pi_flags(args.pi_flag)
            print(
                f"[ralph] Validated {len(args.pi_flag)} pi flag(s): {' '.join(_PI_FLAGS)}"
            )
    run_loop(auto_close=args.auto_close, single_issue=args.issue)
