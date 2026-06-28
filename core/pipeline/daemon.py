"""Pipeline daemon (Phase C final extraction).

Owns ``run_loop`` — the long-running daemon that fetches tickets and
runs ``run_pipeline`` until interrupted.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from typing import Optional

from core.pipeline import recovery as _recovery
from core.pipeline.checkpoint import CHECKPOINT_FILE, clear_checkpoint, save_checkpoint
from core.pipeline.git_ops import commit_stage
from core.pipeline.github.board import sync_closed
from core.pipeline.github.comments import gh_comment
from core.pipeline.github.labels import transition_label
from core.pipeline.issue_ops import (
    fetch_issue_by_number,
    fetch_ready_ticket,
    fetch_retry_issue,
    sync_ready_board,
)
from core.pipeline.providers import ProviderError, _handle_provider_error
from core.pipeline.retry import log_metrics
from core.pipeline.runner import run_pipeline
from core.pipeline.shell import gh, git
from core.pipeline.stages.build import run_build_stage
from core.pipeline.stages.verify import run_verify_stage


def run_loop(auto_close: bool = False, single_issue: Optional[int] = None):
    """
    The daemon loop. Runs until interrupted.

    Args:
        auto_close: If True, close issues on success instead of
                    marking status:review.
        single_issue: If set, process only this issue number and exit.
    """
    if not _recovery.acquire_pid_file():
        sys.exit(1)

    signal.signal(signal.SIGINT, _recovery._handle_signal)
    signal.signal(signal.SIGTERM, _recovery._handle_signal)

    print("[ralph] Daemon started")
    log_metrics("daemon_start")

    try:
        recovered = _recovery.recover_from_crash()
        tried_agents: set[str] = set()

        while not _recovery._shutdown_requested:
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
                        success = run_build_stage(issue, is_retry=True)
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
                if not _recovery._shutdown_requested:
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
                    if _recovery._shutdown_requested:
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
            if not _recovery._shutdown_requested:
                time.sleep(5)

    except _recovery.RalphInterrupted:
        # Graceful shutdown requested; let finally mark the in-flight issue.
        pass
    except Exception as e:
        print(f"[ralph] Unhandled error: {e}")
        log_metrics("daemon_error", error=str(e))
        raise
    finally:
        _recovery._in_cleanup = True
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
        _recovery.release_pid_file()
        log_metrics("daemon_stop")
        print("[ralph] Daemon stopped")
        _recovery._in_cleanup = False


__all__ = ["run_loop"]
