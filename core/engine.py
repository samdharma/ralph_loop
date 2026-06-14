#!/usr/bin/env python3
"""
Ralph v3 — Pipeline Engine

Core loop: fetch ticket → claim → invoke agent → validate → handoff.
Phase 1: single-stage (all-in-one agent per issue).

Usage (via CLI):
    ralph daemon

Sub-modules:
    fetch_ready_ticket()  — Item 2
    run_pipeline()        — Item 3 (single-stage loop)
    transition_label()    — Item 4
    daemon loop           — Item 6
    checkpoint/restore    — Item 7
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
CHECKPOINT_FILE = PROJECT_ROOT / ".ralph" / "checkpoint.json"
PID_FILE = Path("/tmp") / f"ralph_daemon_{PROJECT_ROOT.name}.pid"
LOG_DIR = PROJECT_ROOT / "logs"
METRICS_FILE = LOG_DIR / "ralph_metrics.jsonl"
PROMPT_FILE = PROJECT_ROOT / "docs" / "agent" / "PROMPT.md"
PREFLIGHT_SCRIPT = PROJECT_ROOT / "config" / "ralph_preflight.sh"


# ─────────────────────────────────────────────────────────
# Shell helpers
# ─────────────────────────────────────────────────────────

def run(cmd: list[str], check: bool = True, capture: bool = True,
        timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run a shell command, return CompletedProcess."""
    return subprocess.run(cmd, capture_output=capture, text=True,
                          check=check, timeout=timeout, cwd=PROJECT_ROOT)


def gh(*args: str) -> subprocess.CompletedProcess:
    """Run `gh` command. Raises on failure."""
    return run(["gh", *args])


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
    result = gh("issue", "list",
                "--label", "status:ready",
                "--state", "open",
                "--json", "number,title,body",
                "--limit", "20")

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


def _dependencies_met(issue: dict) -> bool:
    """Check if all 'Depends on: #N' references in the body are closed."""
    body = issue.get("body") or ""
    deps = _parse_depends_on(body)
    for dep_num in deps:
        try:
            result = gh("issue", "view", str(dep_num),
                        "--json", "state",
                        "--jq", ".state")
            state = result.stdout.strip()
            if state != "CLOSED":
                print(f"[ralph] #{issue['number']} depends on #{dep_num} (still {state})")
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

def transition_label(issue_num: int, add: str, remove: Optional[str] = None):
    """Update issue labels via `gh issue edit`."""
    cmd = ["issue", "edit", str(issue_num), "--add-label", add]
    if remove:
        cmd += ["--remove-label", remove]
    gh(*cmd)
    action = f"+{add}"
    if remove:
        action += f" / -{remove}"
    print(f"[ralph] #{issue_num} labels: {action}")


# ─────────────────────────────────────────────────────────
# Item 3: Single-Stage Pipeline
# ─────────────────────────────────────────────────────────

def run_pipeline(issue: dict) -> bool:
    """
    Phase 1: Single-stage pipeline.
    Assembles prompt, invokes agent, runs validation.
    Returns True on success.
    """
    issue_num = issue["number"]
    print(f"\n{'='*50}")
    print(f"[ralph] Pipeline starting for #{issue_num}: {issue['title']}")
    print(f"{'='*50}\n")

    log_metrics("pipeline_start", issue=str(issue_num))

    # ── Pre-flight check ──
    if PREFLIGHT_SCRIPT.exists():
        result = run(["bash", str(PREFLIGHT_SCRIPT)], check=False)
        if result.returncode != 0:
            print(f"[ralph] Pre-flight FAILED for #{issue_num}")
            transition_label(issue_num, "status:blocked", "status:design")
            return False

    # ── Checkpoint: save issue + pre-commit SHA ──
    pre_sha = git("rev-parse", "HEAD").stdout.strip()
    save_checkpoint(issue_num, pre_sha)

    # ── Assemble prompt ──
    prompt = assemble_prompt(issue)

    # ── Invoke agent (all-in-one) ──
    success = invoke_agent(prompt, issue_num)

    # ── Validate ──
    if success:
        print(f"\n[ralph] Running validation gate...")
        val_result = run(
            [sys.executable, str(PROJECT_ROOT / "core" / "validate.py"),
             "--tier", "targeted"],
            check=False, capture=False
        )
        success = (val_result.returncode == 0)

    # ── Handoff ──
    clear_checkpoint()

    if success:
        print(f"\n[ralph] #{issue_num} PASSED — handing off for review")
        transition_label(issue_num, "status:review", "status:design")
        log_metrics("pipeline_complete", issue=str(issue_num), result="review")
    else:
        print(f"\n[ralph] #{issue_num} FAILED — marking blocked")
        transition_label(issue_num, "status:blocked", "status:design")
        log_metrics("pipeline_complete", issue=str(issue_num), result="blocked")

    return success


def assemble_prompt(issue: dict) -> str:
    """Build the all-in-one agent prompt from PROMPT.md + issue body."""
    base = ""
    if PROMPT_FILE.exists():
        base = PROMPT_FILE.read_text(encoding="utf-8")

    body = issue.get("body") or "(No description)"

    # Append reference docs if referenced in body
    ref_docs = _parse_reference_docs(body)
    ref_section = ""
    if ref_docs:
        ref_section = "\n\n## Reference Documentation\n\n"
        for ref in ref_docs:
            ref_path = PROJECT_ROOT / ref
            if ref_path.exists():
                ref_section += f"### {ref}\n\n{ref_path.read_text(encoding='utf-8')}\n\n"
            else:
                ref_section += f"### {ref}\n\n(File not found: {ref})\n\n"

    prompt = (
        f"{base}\n\n"
        f"---\n\n"
        f"## Issue #{issue['number']}: {issue['title']}\n\n"
        f"{body}"
        f"{ref_section}"
        f"\n\n---\n\n"
        f"## Instructions\n\n"
        f"1. Read the issue above carefully.\n"
        f"2. Research the codebase to understand existing patterns.\n"
        f"3. Implement the changes described in the issue.\n"
        f"4. Write tests for all new/changed functionality.\n"
        f"5. Run `ralph validate --tier=targeted` to verify.\n"
        f"6. Commit your changes with a descriptive message.\n"
        f"7. Do NOT modify GitHub labels or issues.\n"
    )
    return prompt


def _parse_reference_docs(body: str) -> list[str]:
    """Extract 'Reference: path/to/doc.md' from issue body."""
    import re
    refs = []
    for line in body.splitlines():
        match = re.search(r"Reference:\s*(\S+)", line, re.IGNORECASE)
        if match:
            refs.append(match.group(1))
    return refs


def invoke_agent(prompt: str, issue_num: int) -> bool:
    """
    Invoke the AI agent (pi or kimi) with the assembled prompt.
    Returns True if agent exits successfully.
    """
    # Detect agent binary
    agent_bin = os.environ.get("RALPH_AGENT", "")
    if not agent_bin:
        for candidate in ["pi", "kimi"]:
            if subprocess.run(["which", candidate], capture_output=True).returncode == 0:
                agent_bin = candidate
                break

    if not agent_bin:
        print("[ralph] ERROR: No AI agent found (pi or kimi). Set RALPH_AGENT.")
        return False

    print(f"[ralph] Invoking {agent_bin} for #{issue_num}...")
    log_metrics("agent_invoke", issue=str(issue_num), agent=agent_bin)

    try:
        if agent_bin == "pi":
            # pi --print for non-interactive mode
            result = run(
                [agent_bin, "--print", prompt],
                check=False, capture=False, timeout=None
            )
        else:
            # kimi
            result = run(
                [agent_bin, "--print", prompt],
                check=False, capture=False, timeout=None
            )
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

def save_checkpoint(issue_num: int, pre_sha: str):
    """Save checkpoint for crash recovery."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "issue": issue_num,
        "pre_commit_sha": pre_sha,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2))


def clear_checkpoint():
    """Remove checkpoint file on clean completion."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


def recover_from_crash():
    """
    Check for interrupted work from previous run.
    If found: roll back to pre-commit SHA, mark issue blocked, clear checkpoint.
    """
    if not CHECKPOINT_FILE.exists():
        return

    print("[ralph] Found checkpoint from previous run — recovering...")
    try:
        data = json.loads(CHECKPOINT_FILE.read_text())
        issue_num = data["issue"]
        pre_sha = data.get("pre_commit_sha", "")

        # Roll back to pre-pipeline state
        if pre_sha:
            print(f"[ralph] Rolling back to commit {pre_sha[:8]}...")
            git("checkout", pre_sha)

        # Mark issue as blocked (interrupted)
        try:
            transition_label(issue_num, "status:blocked", "status:design")
            # Add a comment about the interruption
            gh("issue", "comment", str(issue_num),
               "--body", "⚠️ Ralph was interrupted while processing this issue. "
                         "Please review and re-mark as `status:ready` if still needed.")
        except subprocess.CalledProcessError:
            print(f"[ralph] Could not update #{issue_num} — continuing anyway")

        log_metrics("crash_recovery", issue=str(issue_num))
    except Exception as e:
        print(f"[ralph] Recovery error: {e}")
    finally:
        clear_checkpoint()


# ─────────────────────────────────────────────────────────
# Item 6: Daemon Wrapper
# ─────────────────────────────────────────────────────────

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    print(f"\n[ralph] Received {sig_name} — shutting down gracefully...")
    _shutdown_requested = True


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


def run_loop():
    """The daemon loop. Runs until interrupted."""
    if not acquire_pid_file():
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print("[ralph] Daemon started")
    log_metrics("daemon_start")

    try:
        recover_from_crash()

        while not _shutdown_requested:
            # ── Sync ──
            print("[ralph] Syncing with remote...")
            try:
                git("fetch", "origin")
                git("merge", "origin/main", "--ff-only")
            except subprocess.CalledProcessError:
                print("[ralph] Warning: git sync failed — continuing with local state")

            # ── Fetch next ready ticket ──
            issue = fetch_ready_ticket()
            if issue is None:
                print("[ralph] No ready tickets. Sleeping...")
                log_metrics("daemon_idle")
                # Sleep with interrupt check
                for _ in range(60):  # Check every second for shutdown
                    if _shutdown_requested:
                        break
                    time.sleep(1)
                continue

            # ── Claim & Pipeline ──
            issue_num = issue["number"]
            transition_label(issue_num, "status:design", "status:ready")
            run_pipeline(issue)

            # Brief pause between issues
            if not _shutdown_requested:
                time.sleep(5)

    except Exception as e:
        print(f"[ralph] Unhandled error: {e}")
        log_metrics("daemon_error", error=str(e))
        raise
    finally:
        release_pid_file()
        log_metrics("daemon_stop")
        print("[ralph] Daemon stopped")


# ─────────────────────────────────────────────────────────
# CLI entry point for direct invocation (ralph daemon calls this)
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_loop()
