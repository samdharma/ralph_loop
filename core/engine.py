#!/usr/bin/env python3
"""
Ralph v3 — Pipeline Engine

Core loop: fetch ticket → claim → DESIGN → BUILD → VERIFY → handoff.
Phase 2: 3-stage pipeline with distinct persona prompts per stage.

Usage (via CLI):
    ralph daemon
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from core.project_sync import sync_status  # noqa: F401
from core.project_sync import sync_closed

# Ensure the project root (parent of ``core/``) is on sys.path so
# ``from core.pipeline.state import ...`` works whether engine.py is
# invoked as ``python core/engine.py`` (bin/ralph flow) or as
# ``python -m core.engine``. Without this, the package import fails
# in the bin/ralph flow because only ``core/`` (not its parent) is
# on sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Phase C follow-up: ticket fetchers, prompt builders, test tracking,
# git helpers, reporting, and artifact helpers now live in dedicated
# pipeline modules. Engine re-exports them for backward compatibility.
from core.pipeline.artifacts_ops import (  # noqa: E402,F401
    _archive_issue_artifacts,
    _archived_issue_dir,
    _cleanup_issue_artifacts,
    _design_spec_path,
)

# CHECKPOINT_FILE lives in core.pipeline.checkpoint (C1 step 2);
# engine.py re-imports it for backward compatibility.
from core.pipeline.checkpoint import CHECKPOINT_FILE  # noqa: E402,F401
from core.pipeline.git_ops import (  # noqa: E402,F401
    _has_commits,
    _has_unpushed_commits,
    _push_with_retry,
    _rollback_working_tree,
    commit_stage,
)
from core.pipeline.issue_ops import (  # noqa: E402,F401
    RETRY_LABEL_MAP,
    _dependencies_met,
    _parse_depends_on,
    fetch_issue_by_number,
    fetch_ready_ticket,
    fetch_retry_issue,
    sync_ready_board,
)
from core.pipeline.prompts import (  # noqa: E402,F401
    _assemble_subagent_prompt,
    _fetch_issue_comments,
    _parse_reference_docs,
    assemble_stage_prompt,
)

# PID_FILE lives in core.pipeline.recovery (C1 step 3); engine.py
# re-imports it for backward compatibility.
from core.pipeline.recovery import PID_FILE  # noqa: E402,F401
from core.pipeline.reporting import (  # noqa: E402,F401
    _extract_failure_summary,
    _format_stage_failure,
    _read_partial_design_spec,
    _summarize_design_spec,
    _write_stage_report,
)

# Canonical project-path constants and shell wrappers live in
# core.pipeline.shell (Phase C follow-up). Engine re-exports them
# so existing ``from core.engine import X`` callers keep working.
from core.pipeline.shell import (  # noqa: E402,F401
    DESIGN_SPEC_DIR,
    LOG_DIR,
    METRICS_FILE,
    PREFLIGHT_SCRIPT,
    PROJECT_ROOT,
    PROMPT_FILE,
    PROMPTS_DIR,
    gh,
    git,
    run,
)

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
from core.pipeline.test_tracking import (  # noqa: E402,F401
    TamperedTestsError,
    _detect_new_tests,
    _detect_tampered_tests,
    _file_hash,
    _load_test_tracking,
    _resolve_existing_test_paths,
    _save_test_tracking,
    _snapshot_file_hashes,
    _snapshot_tests_dir,
    _test_tracking_file,
)

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────


# Extra flags passed to pi via --pi-flag (validated at startup against pi --help).
# Each string may contain multiple whitespace-separated tokens.
_PI_FLAGS: list[str] = []

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
# C1 step 4 — github/comments.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# gh_comment lives at core.pipeline.github.comments (per spec §6.1,
# §10.3 C1). It is re-imported here so existing callers that
# ``from core.engine import gh_comment`` continue to work. New code
# should import directly from core.pipeline.github.comments.
from core.pipeline.github.comments import gh_comment  # noqa: E402,F401

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
# Phase C extraction — BUILD / VERIFY stage re-exports
# ─────────────────────────────────────────────────────────
# run_build_stage, run_verify_stage, and their sub-agent helpers now
# live in core.pipeline.stages.build, core.pipeline.stages.verify, and
# core.pipeline.stages.build_subagents respectively. They are re-imported
# here so existing callers that ``from core.engine import X`` continue to
# work. New code should import directly from the stage modules.
from core.pipeline.stages.build import run_build_stage  # noqa: E402,F401
from core.pipeline.stages.build_subagents import (  # noqa: E402,F401
    _run_implement_subagent,
    _run_test_subagent,
)

# ─────────────────────────────────────────────────────────
# C1 step 10 — stages/design.py re-exports (per plan §1.1 C1)
# ─────────────────────────────────────────────────────────
# run_design_stage lives at core.pipeline.stages.design (per spec
# §6.1, §10.3 C1). It is re-imported here so existing callers that
# ``from core.engine import run_design_stage`` continue to work.
# New code should import directly from core.pipeline.stages.design.
from core.pipeline.stages.design import run_design_stage  # noqa: E402,F401
from core.pipeline.stages.verify import run_verify_stage  # noqa: E402,F401

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
