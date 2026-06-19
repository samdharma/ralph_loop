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
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from project_sync import _get_config, sync_closed, sync_status

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
CHECKPOINT_FILE = PROJECT_ROOT / ".ralph" / "checkpoint.json"
PID_FILE = Path("/tmp") / f"ralph_daemon_{PROJECT_ROOT.name}.pid"
LOG_DIR = PROJECT_ROOT / "logs"
METRICS_FILE = LOG_DIR / "ralph_metrics.jsonl"
PROMPT_FILE = PROJECT_ROOT / "docs" / "agent" / "PROMPT.md"
PROGRESS_FILE = PROJECT_ROOT / "docs" / "agent" / "PROGRESS.md"
PROMPTS_DIR = PROJECT_ROOT / "docs" / "agent" / "prompts"
PREFLIGHT_SCRIPT = PROJECT_ROOT / "config" / "ralph_preflight.sh"


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


def gh_comment(issue_num: int, body: str) -> bool:
    """Post a comment on the GitHub issue. Fail-soft."""
    try:
        gh("issue", "comment", str(issue_num), "--body", body)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ralph] WARNING: could not comment on #{issue_num}: {e}")
        return False


def git(*args: str) -> subprocess.CompletedProcess:
    """Run `git` command. Raises on failure."""
    return run(["git", *args])


# ─────────────────────────────────────────────────────────
# Metrics logging
# ─────────────────────────────────────────────────────────


def log_metrics(event: str, **kwargs):
    """Append a structured metrics event to ralph_metrics.jsonl."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


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


def transition_label(
    issue_num: int,
    add: str,
    remove: Optional[str] = None,
    retries: int = 3,
    backoff: float = 2.0,
):
    """Update issue labels via `gh issue edit`. Retries on transient failures."""
    cmd = ["issue", "edit", str(issue_num), "--add-label", add]
    if remove:
        cmd += ["--remove-label", remove]

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            gh(*cmd)
            action = f"+{add}"
            if remove:
                action += f" / -{remove}"
            print(f"[ralph] #{issue_num} labels: {action}")
            # Mirror the new label to the GitHub Project board column.
            sync_status(issue_num, add)
            return
        except subprocess.CalledProcessError as e:
            last_error = e
            if attempt < retries:
                wait = backoff**attempt
                print(
                    f"[ralph] Label transition failed (attempt {attempt}/{retries}), "
                    f"retrying in {wait:.0f}s..."
                )
                _check_interrupt()
                time.sleep(wait)
    # All retries exhausted
    raise last_error


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
    session_file = PROJECT_ROOT / ".ralph" / f"session-{issue_num}.jsonl"

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
            "Using existing `docs/agent/PROGRESS.md`.",
        )
    else:
        save_checkpoint(issue_num, "design")
        if not run_design_stage(issue):
            clear_checkpoint()
            _cleanup_issue_artifacts(issue_num)
            partial_spec = _read_partial_design_spec()
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
        design_summary = _summarize_design_spec()
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
        if not run_build_stage(issue):
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
    verify_pass = run_verify_stage(issue)
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
            gh_comment(issue_num, "✅ VERIFY passed. Handing off for human review.")
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
        log_metrics(
            "pipeline_complete", issue=str(issue_num), result="blocked", stage="verify"
        )

    return verify_pass


# ─────────────────────────────────────────────────────────
# Stage runners
# ─────────────────────────────────────────────────────────


def run_design_stage(issue: dict) -> bool:
    """STAGE 1: Architect persona — reads issue + codebase, writes design spec.
    Saves session file for Mode B sub-agent context inheritance."""
    issue_num = issue["number"]
    print(f"\n[ralph] STAGE 1/3: DESIGN for #{issue_num}")
    gh_comment(issue_num, "🎨 DESIGN stage started.")
    log_metrics("stage_start", issue=str(issue_num), stage="design")

    session_file = PROJECT_ROOT / ".ralph" / f"session-{issue_num}.jsonl"
    prompt = assemble_stage_prompt(issue, "design.md")
    success = invoke_agent(prompt, issue_num, session_file=session_file)

    log_metrics("stage_complete", issue=str(issue_num), stage="design")
    return success


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

    # ── Validation gate (only tests written by the independent QA session) ──
    print(f"\n[ralph] Running validation gate...")
    core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parent))
    qa_tests = _load_test_tracking(issue_num)
    qa_tests = [t for t in qa_tests if t.endswith(".py")]  # Defense: skip cache artifacts
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
    """
    issue_num = issue["number"]
    print(f"\n[ralph] STAGE 3/3: VERIFY for #{issue_num}")
    gh_comment(issue_num, "🔍 VERIFY stage started (independent review).")
    log_metrics(
        "stage_start", issue=str(issue_num), stage="verify", subagent="verify", mode="A"
    )

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
        prompt += f"\n\n## Git Diff (changes to review)\n\n```diff\n{diff[:8000]}\n```"
        if len(diff) > 8000:
            prompt += "\n\n(…diff truncated — review key files from the repo)"

    success = invoke_agent(prompt, issue_num)
    if success:
        gh_comment(issue_num, "✅ VERIFY review sub-agent completed.")
    else:
        gh_comment(issue_num, "❌ VERIFY review sub-agent failed.")
    log_metrics(
        "subagent_complete",
        issue=str(issue_num),
        subagent="verify",
        mode="A",
        result="success" if success else "failure",
    )

    # Run validation gate after review (only tests written by the independent QA session)
    if success:
        print(f"\n[ralph] Running validation gate...")
        core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parent))
        qa_tests = _load_test_tracking(issue_num)
        qa_tests = [t for t in qa_tests if t.endswith(".py")]  # Defense: skip cache artifacts
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
            gh_comment(issue_num, "✅ VERIFY validation gate passed.")
        else:
            gh_comment(issue_num, "❌ VERIFY validation gate failed.")
            # Echo output to terminal and capture for report
            val_output = (val_result.stdout or "") + "\n" + (val_result.stderr or "")
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
    return success


# ─────────────────────────────────────────────────────────
# Sub-Agent Methods (Phase 3)
# ─────────────────────────────────────────────────────────


def _run_test_subagent(issue: dict) -> bool:
    """
    TEST sub-agent — Mode A (isolated, fresh session).
    Sees design spec ONLY. Writes tests that SHOULD FAIL.
    No implementation code visibility.
    Snapshots tests/ before and after so VERIFY can run only these QA-written tests.
    """
    issue_num = issue["number"]
    print(f"\n  [ralph] BUILD / TEST sub-agent for #{issue_num} (Mode A — isolated)")
    gh_comment(issue_num, "🧪 TEST sub-agent started (isolated).")
    log_metrics("subagent_start", issue=str(issue_num), subagent="test", mode="A")

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


def _write_stage_report(
    issue_num: int, stage: str, failed_step: str, output: str
):
    """Write a failure report file following the Failure Reporting Contract."""
    report_path = PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Truncate if enormous (GitHub comments already have their own limit)
    max_output = 50000
    if len(output) > max_output:
        output = (
            output[:max_output].rstrip()
            + "\n\n_(output truncated for report file)_"
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
        f"- Design spec: `docs/agent/PROGRESS.md`\n"
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
    """Discard all uncommitted changes so stale files don't pollute later stages."""
    try:
        # Remove untracked files first
        run(["git", "clean", "-fd"], check=False, capture=True)
        # Reset tracked files to HEAD
        run(["git", "checkout", "--", "."], check=False, capture=True)
        print("[ralph] Working tree rolled back after BUILD failure.")
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


def _test_tracking_file(issue_num: int) -> Path:
    return PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-tests.json"


def _save_test_tracking(issue_num: int, test_paths: list[str]):
    """Persist the list of test files created during the TEST stage."""
    path = _test_tracking_file(issue_num)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tests": test_paths}, indent=2))


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


def _summarize_design_spec() -> Optional[str]:
    """Read PROGRESS.md and return a condensed design summary for an issue comment."""
    if not PROGRESS_FILE.exists():
        return None
    text = PROGRESS_FILE.read_text(encoding="utf-8")
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
    out.append("**Files:** See [`docs/agent/PROGRESS.md`](docs/agent/PROGRESS.md)")
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
    out.append("Full design spec committed to `docs/agent/PROGRESS.md`.")
    return "\n".join(out)


def _read_partial_design_spec(max_chars: int = 2000) -> Optional[str]:
    """Read PROGRESS.md if it exists (including partial/incomplete specs).
    Returns truncated content or None if the file doesn't exist."""
    if not PROGRESS_FILE.exists():
        return None
    try:
        text = PROGRESS_FILE.read_text(encoding="utf-8").strip()
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
) -> str:
    """Build a detailed stage-failure comment with pointers to artifacts."""
    lines = [f"❌ {stage} stage failed.", ""]
    lines.append(
        "See [`docs/agent/PROGRESS.md`](docs/agent/PROGRESS.md) for the design spec."
    )
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

    # Design spec (Mode A only — Mode B already has it in session context)
    if mode == "A" and PROGRESS_FILE.exists():
        design_spec = PROGRESS_FILE.read_text(encoding="utf-8")
        prompt += f"\n\n## Design Spec (from DESIGN stage)\n\n{design_spec}"

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


def _resolve_agent_binary() -> str:
    """
    Determine which AI agent binary to invoke.

    Resolution order:
      1. RALPH_AGENT environment variable.
      2. [agent].binary in .ralph/config.toml.
      3. First available binary on PATH: pi, then kimi.

    Returns an empty string if no agent can be resolved.
    """
    # 1. Environment override
    agent_bin = os.environ.get("RALPH_AGENT", "").strip()
    if agent_bin:
        return agent_bin

    # 2. Project config
    try:
        config = _get_config()
        configured = config.get("agent", {}).get("binary", "").strip()
        if configured:
            return configured
    except Exception:
        pass

    # 3. Auto-detect from PATH
    for candidate in ["pi", "kimi"]:
        if subprocess.run(["which", candidate], capture_output=True).returncode == 0:
            return candidate

    return ""


def _get_kimi_session_id(project_root: Path) -> Optional[str]:
    """
    Find the most recent Kimi session ID for the project working directory.

    Kimi stores a session index at <kimi-home>/session_index.jsonl. Each line
    maps a workDir to a sessionId. We look for the latest entry whose workDir
    matches the project root.
    """
    try:
        result = subprocess.run(
            ["which", "kimi"], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            return None

        # Derive Kimi home from the binary location, e.g. ~/.kimi-code/bin/kimi
        kimi_bin = Path(result.stdout.strip())
        kimi_home = kimi_bin.parent.parent
        index_file = kimi_home / "session_index.jsonl"
        if not index_file.exists():
            return None

        target = project_root.resolve()
        session_id = None
        with open(index_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_workdir = entry.get("workDir")
                    if entry_workdir and Path(entry_workdir).resolve() == target:
                        session_id = entry.get("sessionId")
                except (json.JSONDecodeError, OSError):
                    continue
        return session_id
    except Exception:
        return None


def invoke_agent(
    prompt: str,
    issue_num: int,
    session_file: Optional[Path] = None,
    continue_session: bool = False,
) -> bool:
    """
    Invoke the AI agent (pi or kimi) with the assembled prompt.

    Args:
        prompt: The assembled prompt text.
        issue_num: GitHub issue number (for logging).
        session_file: If set, save/use this session identifier.
            pi: path to a session file created/continued by pi.
            kimi: path to a text file containing the Kimi session UUID.
        continue_session: If True, inherit prior session context (Mode B).
            pi: uses --continue --session <file>.
            kimi: reads the stored session UUID from session_file and passes
                  --session <id> to resume DESIGN context explicitly.

    Returns True if agent exits successfully.
    """
    # Detect agent binary
    agent_bin = _resolve_agent_binary()
    if not agent_bin:
        print(
            "[ralph] ERROR: No AI agent found (pi or kimi). "
            "Set [agent].binary in .ralph/config.toml or set RALPH_AGENT."
        )
        return False

    mode_str = " (continue)" if continue_session else ""
    print(f"[ralph] Invoking {agent_bin} for #{issue_num}{mode_str}...")
    log_metrics(
        "agent_invoke",
        issue=str(issue_num),
        agent=agent_bin,
        continue_session=continue_session,
    )

    try:
        if agent_bin == "pi":
            cmd = [agent_bin, "--print"]
            if session_file:
                cmd += ["--session", str(session_file)]
            if continue_session:
                cmd += ["--continue"]
            cmd.append(prompt)
            result = run(cmd, check=False, capture=False, timeout=None)
            _check_interrupt()
        elif agent_bin == "kimi":
            # kimi uses --prompt for non-interactive prompt mode (pi uses --print).
            # --prompt mode already runs under the auto permission policy, so no -y/--yolo
            # flag is needed (and kimi 0.16+ rejects combining --prompt with --yolo).
            # Mode B must resume the DESIGN session explicitly. kimi --continue would
            # resume the most recent session for the working directory, which after TEST
            # is the TEST session, not DESIGN. We save the DESIGN session UUID after
            # DESIGN completes and pass it via --session for IMPLEMENT.
            if continue_session:
                if not session_file:
                    print(
                        "[ralph] ERROR: kimi Mode B requires a session_file to resume DESIGN context."
                    )
                    return False
                if not session_file.exists():
                    print(
                        f"[ralph] ERROR: No saved Kimi session to continue for #{issue_num}."
                    )
                    return False
                design_session_id = session_file.read_text(encoding="utf-8").strip()
                if not design_session_id:
                    print(
                        f"[ralph] ERROR: Saved Kimi session ID is empty for #{issue_num}."
                    )
                    return False
                print(
                    f"[ralph] Resuming Kimi session {design_session_id} for #{issue_num}..."
                )
                cmd = [agent_bin, "--prompt", prompt, "--session", design_session_id]
            else:
                cmd = [agent_bin, "--prompt", prompt]
            result = run(cmd, check=False, capture=False, timeout=None)
            _check_interrupt()
            # After a successful kimi invocation that should establish context (DESIGN),
            # capture the session UUID so Mode B can resume it explicitly.
            if result.returncode == 0 and session_file and not continue_session:
                session_id = _get_kimi_session_id(PROJECT_ROOT)
                if session_id:
                    session_file.parent.mkdir(parents=True, exist_ok=True)
                    session_file.write_text(session_id, encoding="utf-8")
                    print(f"[ralph] Saved Kimi session {session_id} for #{issue_num}")
                else:
                    print(
                        f"[ralph] WARNING: Could not determine Kimi session ID for #{issue_num}. "
                        "Mode B continuation may fail."
                    )
        else:
            print(f"[ralph] ERROR: Unknown agent '{agent_bin}'")
            return False
        _check_interrupt()
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[ralph] Agent timed out for #{issue_num}")
        return False
    except Exception as e:
        print(f"[ralph] Agent invocation error: {e}")
        return False


# ─────────────────────────────────────────────────────────
# Item 7: Checkpoint & Crash Recovery
# ─────────────────────────────────────────────────────────


def save_checkpoint(issue_num: int, stage: str):
    """Save checkpoint for crash recovery with stage info."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    pre_sha = git("rev-parse", "HEAD").stdout.strip()
    data = {
        "issue": issue_num,
        "stage": stage,
        "pre_stage_sha": pre_sha,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2))


def clear_checkpoint():
    """Remove checkpoint file on clean completion."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


def recover_from_crash() -> Optional[dict]:
    """
    Check for interrupted work from previous run.
    If found: roll back to pre-stage SHA, return issue dict for resume.
    Returns None if no crash recovery needed.
    """
    if not CHECKPOINT_FILE.exists():
        return None

    print("[ralph] Found checkpoint from previous run — recovering...")
    try:
        data = json.loads(CHECKPOINT_FILE.read_text())
        issue_num = data["issue"]
        stage = data.get("stage", "design")
        pre_sha = data.get("pre_stage_sha", "")

        # Roll back to pre-stage state (stay on the current branch)
        if pre_sha:
            print(f"[ralph] Rolling back to commit {pre_sha[:8]} (before {stage})...")
            git("reset", "--hard", pre_sha)

        # Fetch the issue body so we can resume
        result = gh("issue", "view", str(issue_num), "--json", "number,title,body")
        issue = json.loads(result.stdout)

        # Item 3: Re-apply the correct status:<stage> label after rollback.
        stage_label_map = {
            "design": "status:design",
            "build": "status:build",
            "verify": "status:verify",
        }
        target_label = stage_label_map.get(stage, "status:design")
        # Remove any stale status labels, then add the correct one
        for lbl in [
            "status:design",
            "status:build",
            "status:verify",
            "status:ready",
            "status:review",
            "status:blocked",
        ]:
            if lbl != target_label:
                try:
                    gh("issue", "edit", str(issue_num), "--remove-label", lbl)
                except subprocess.CalledProcessError:
                    pass  # Label wasn't present — fine
        try:
            gh("issue", "edit", str(issue_num), "--add-label", target_label)
        except subprocess.CalledProcessError as e:
            print(f"[ralph] Warning: could not apply label {target_label}: {e}")

        print(
            f"[ralph] Resuming #{issue_num} at stage: {stage} (label: {target_label})"
        )
        log_metrics("crash_recovery", issue=str(issue_num), stage=stage)

        return {"issue": issue, "resume_stage": stage}

    except Exception as e:
        print(f"[ralph] Recovery error: {e}")
        clear_checkpoint()
        return None


# ─────────────────────────────────────────────────────────
# Item 6: Daemon Wrapper
# ─────────────────────────────────────────────────────────

_shutdown_requested = False
_in_cleanup = False


class RalphInterrupted(BaseException):
    """Raised when the daemon receives SIGINT/SIGTERM during a stage."""

    pass


def _handle_signal(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    print(f"\n[ralph] Received {sig_name} — shutting down gracefully...")
    _shutdown_requested = True


def _check_interrupt():
    """Abort the current operation if a shutdown signal has been received."""
    global _in_cleanup
    if _shutdown_requested and not _in_cleanup:
        raise RalphInterrupted()


def acquire_pid_file() -> bool:
    """Create PID file. Returns False if another daemon is already running."""
    if PID_FILE.exists():
        old_pid = PID_FILE.read_text().strip()
        # Check if the process is still alive
        try:
            os.kill(int(old_pid), 0)
            print(f"[ralph] Daemon already running (PID {old_pid}). Exiting.")
            return False
        except (OSError, ValueError):
            # Stale PID file — remove it
            PID_FILE.unlink()

    PID_FILE.write_text(str(os.getpid()))
    return True


def release_pid_file():
    """Remove PID file on exit."""
    if PID_FILE.exists():
        PID_FILE.unlink()


def run_loop(auto_close: bool = False):
    """
    The daemon loop. Runs until interrupted.

    Args:
        auto_close: If True, close issues on success instead of
                    marking status:review.
    """
    if not acquire_pid_file():
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print("[ralph] Daemon started")
    log_metrics("daemon_start")

    try:
        recovered = recover_from_crash()

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
                    success = run_build_stage(issue)
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
                    verify_pass = run_verify_stage(issue)
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
                                "✅ Resumed VERIFY passed. Handing off for human review.",
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
                    run_pipeline(issue, auto_close=auto_close)
                    continue

                recovered = None
                continue

            # ── Check retry labels first (smallest scope = fastest) ──
            retry = fetch_retry_issue()
            if retry is not None:
                issue, resume_stage = retry
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
                run_pipeline(issue, auto_close=auto_close, resume_stage=resume_stage)
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
            issue_num = issue["number"]
            transition_label(issue_num, "status:design", "status:ready")
            gh_comment(
                issue_num, f"⏳ Ralph claimed issue #{issue_num} and started DESIGN."
            )
            run_pipeline(issue, auto_close=auto_close)

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
    import argparse

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
    args = parser.parse_args()
    if args.agent:
        os.environ["RALPH_AGENT"] = args.agent
    run_loop(auto_close=args.auto_close)
