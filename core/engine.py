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
PROGRESS_FILE = PROJECT_ROOT / "docs" / "agent" / "PROGRESS.md"
PROMPTS_DIR = PROJECT_ROOT / "docs" / "agent" / "prompts"
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
    Phase 2: 3-stage pipeline (DESIGN → BUILD → VERIFY).
    Each stage gets its own persona prompt and commits independently.
    Returns True on success (issue goes to review).
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

    # ── STAGE 1: DESIGN ──
    save_checkpoint(issue_num, "design")
    if not run_design_stage(issue):
        clear_checkpoint()
        transition_label(issue_num, "status:blocked", "status:design")
        log_metrics("pipeline_complete", issue=str(issue_num), result="blocked", stage="design")
        return False
    commit_stage(issue_num, "design")
    transition_label(issue_num, "status:build", "status:design")

    # ── STAGE 2: BUILD ──
    save_checkpoint(issue_num, "build")
    if not run_build_stage(issue):
        clear_checkpoint()
        transition_label(issue_num, "status:blocked", "status:build")
        log_metrics("pipeline_complete", issue=str(issue_num), result="blocked", stage="build")
        return False
    commit_stage(issue_num, "build")
    transition_label(issue_num, "status:verify", "status:build")

    # ── STAGE 3: VERIFY ──
    save_checkpoint(issue_num, "verify")
    verify_pass = run_verify_stage(issue)
    clear_checkpoint()

    if verify_pass:
        print(f"\n[ralph] #{issue_num} PASSED — handing off for review")
        transition_label(issue_num, "status:review", "status:verify")
        log_metrics("pipeline_complete", issue=str(issue_num), result="review")
    else:
        print(f"\n[ralph] #{issue_num} FAILED VERIFY — marking blocked")
        transition_label(issue_num, "status:blocked", "status:verify")
        log_metrics("pipeline_complete", issue=str(issue_num), result="blocked", stage="verify")

    return verify_pass


# ─────────────────────────────────────────────────────────
# Stage runners
# ─────────────────────────────────────────────────────────

def run_design_stage(issue: dict) -> bool:
    """STAGE 1: Architect persona — reads issue + codebase, writes design spec."""
    issue_num = issue["number"]
    print(f"\n[ralph] STAGE 1/3: DESIGN for #{issue_num}")
    log_metrics("stage_start", issue=str(issue_num), stage="design")

    prompt = assemble_stage_prompt(issue, "design.md")
    success = invoke_agent(prompt, issue_num)

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
    log_metrics("stage_start", issue=str(issue_num), stage="build")

    # Run pre-flight before build
    if PREFLIGHT_SCRIPT.exists():
        result = run(["bash", str(PREFLIGHT_SCRIPT)], check=False)
        if result.returncode != 0:
            print(f"[ralph] Pre-flight FAILED for #{issue_num}")
            return False

    # ── Step 2a: TEST sub-agent (Mode A — isolated) ──
    if not _run_test_subagent(issue):
        return False

    # ── Step 2b: IMPLEMENT sub-agent (Mode B — full context) ──
    if not _run_implement_subagent(issue):
        return False

    # ── Validation gate ──
    print(f"\n[ralph] Running validation gate...")
    core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parent))
    val_result = run(
        [sys.executable, os.path.join(core_dir, "validate.py"),
         "--tier", "targeted"],
        check=False, capture=False
    )
    success = (val_result.returncode == 0)

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
    log_metrics("stage_start", issue=str(issue_num), stage="verify",
                subagent="verify", mode="A")

    # Get the git diff for the reviewer to inspect
    pre_sha = git("rev-parse", "HEAD~1").stdout.strip() if _has_commits() else git("rev-parse", "HEAD").stdout.strip()
    diff = git("diff", pre_sha, "HEAD").stdout if _has_commits() else ""

    # Mode A: assemble prompt with minimal context (no codebase reference)
    prompt = _assemble_subagent_prompt(issue, "verify.md", mode="A")

    # Include git diff
    if diff:
        prompt += f"\n\n## Git Diff (changes to review)\n\n```diff\n{diff[:8000]}\n```"
        if len(diff) > 8000:
            prompt += "\n\n(…diff truncated — review key files from the repo)"

    success = invoke_agent(prompt, issue_num)
    log_metrics("subagent_complete", issue=str(issue_num), subagent="verify",
                mode="A", result="success" if success else "failure")

    # Run validation gate after review
    if success:
        print(f"\n[ralph] Running validation gate...")
        core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parent))
        val_result = run(
            [sys.executable, os.path.join(core_dir, "validate.py"),
             "--tier", "targeted"],
            check=False, capture=False
        )
        success = (val_result.returncode == 0)

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
    """
    issue_num = issue["number"]
    print(f"\n  [ralph] BUILD / TEST sub-agent for #{issue_num} (Mode A — isolated)")
    log_metrics("subagent_start", issue=str(issue_num), subagent="test", mode="A")

    prompt = _assemble_subagent_prompt(issue, "test.md", mode="A")
    success = invoke_agent(prompt, issue_num)

    log_metrics("subagent_complete", issue=str(issue_num), subagent="test",
                mode="A", result="success" if success else "failure")
    return success


def _run_implement_subagent(issue: dict) -> bool:
    """
    IMPLEMENT sub-agent — Mode B (full context).
    Sees design spec + test files + codebase. Writes implementation code.
    """
    issue_num = issue["number"]
    print(f"\n  [ralph] BUILD / IMPLEMENT sub-agent for #{issue_num} (Mode B — full context)")
    log_metrics("subagent_start", issue=str(issue_num), subagent="implement", mode="B")

    prompt = _assemble_subagent_prompt(issue, "implement.md", mode="B")

    # Include test files that were just written by TEST sub-agent
    test_files = _discover_test_files()
    if test_files:
        prompt += "\n\n## Test Files (from QA sub-agent)\n\n"
        prompt += "These tests were written by an independent QA sub-agent who never "
        prompt += "saw the codebase. They should be failing. Your job is to make them pass.\n\n"
        for tf in sorted(test_files):
            try:
                content = tf.read_text(encoding="utf-8")
                prompt += f"### {tf.relative_to(PROJECT_ROOT)}\n\n```python\n{content[:5000]}\n```\n\n"
                if len(content) > 5000:
                    prompt += "(…file truncated — read full file in repo)\n\n"
            except Exception:
                prompt += f"### {tf.relative_to(PROJECT_ROOT)}\n(Unable to read)\n\n"
    else:
        prompt += "\n\n(No new test files detected — check tests/ directory)\n"

    success = invoke_agent(prompt, issue_num)

    log_metrics("subagent_complete", issue=str(issue_num), subagent="implement",
                mode="B", result="success" if success else "failure")
    return success


def _discover_test_files() -> list[Path]:
    """
    Find test files that were created or modified since the last commit.
    Used to inject test content into the IMPLEMENT sub-agent prompt.
    """
    test_files = []
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        return test_files

    try:
        # Get files changed since last commit
        result = git("diff", "--name-only", "HEAD")
        changed = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()

        # Also get untracked files in tests/
        result2 = git("ls-files", "--others", "--exclude-standard", "tests/")
        untracked = set(result2.stdout.strip().split("\n")) if result2.stdout.strip() else set()

        all_changed = changed | untracked
        for fpath in all_changed:
            p = PROJECT_ROOT / fpath
            if p.exists() and p.suffix == ".py":
                test_files.append(p)
    except Exception:
        # Fallback: scan tests/ directory for .py files
        for p in tests_dir.rglob("*.py"):
            test_files.append(p)

    return test_files


def _has_commits() -> bool:
    """Check if the repo has any commits (vs. fresh repo)."""
    try:
        result = git("rev-list", "--count", "HEAD")
        return int(result.stdout.strip()) >= 2
    except Exception:
        return False


def _assemble_subagent_prompt(issue: dict, stage_prompt_file: str, mode: str) -> str:
    """
    Build a prompt for a sub-agent invocation.

    Mode A (Isolated): issue body + design spec + stage persona ONLY.
      No codebase context, no reference docs. Fresh perspective.
      Used for TEST and VERIFY sub-agents.

    Mode B (Full context): issue body + design spec + reference docs + stage persona.
      Full context for implementation work.
      Used for IMPLEMENT sub-agent.
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
    prompt = (
        f"{base}\n\n"
        f"---\n\n"
        f"## Sub-Agent Instructions\n\n"
        f"{stage_prompt}\n\n"
        f"---\n\n"
        f"## Issue #{issue['number']}: {issue['title']}\n\n"
        f"{body}"
    )

    # Design spec (all modes need it)
    if PROGRESS_FILE.exists():
        design_spec = PROGRESS_FILE.read_text(encoding="utf-8")
        prompt += f"\n\n## Design Spec (from DESIGN stage)\n\n{design_spec}"

    # Reference docs — Mode B only (IMPLEMENT sub-agent)
    if mode == "B":
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
                ref_section += f"### {ref}\n\n{ref_path.read_text(encoding='utf-8')}\n\n"
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
    return prompt


def commit_stage(issue_num: int, stage: str):
    """Commit all changes after a pipeline stage completes."""
    msg = f"[ralph] {stage}: #{issue_num}"
    try:
        git("add", "-A")
        git("commit", "-m", msg)
        print(f"[ralph] Committed: {msg}")
    except subprocess.CalledProcessError:
        # No changes to commit (e.g., DESIGN stage may not change files)
        print(f"[ralph] Nothing to commit for {stage}")


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

        # Roll back to pre-stage state
        if pre_sha:
            print(f"[ralph] Rolling back to commit {pre_sha[:8]} (before {stage})...")
            git("checkout", pre_sha)

        # Fetch the issue body so we can resume
        result = gh("issue", "view", str(issue_num),
                    "--json", "number,title,body")
        issue = json.loads(result.stdout)

        # Restore the correct label for this stage
        stage_label_map = {
            "design": "status:design",
            "build": "status:build",
            "verify": "status:verify",
        }
        current_label = stage_label_map.get(stage, "status:design")

        print(f"[ralph] Resuming #{issue_num} at stage: {stage}")
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
                    save_checkpoint(issue_num, "build")
                    success = run_build_stage(issue)
                    if not success:
                        transition_label(issue_num, "status:blocked", "status:build")
                        clear_checkpoint()
                        recovered = None
                        continue
                    commit_stage(issue_num, "build")
                    transition_label(issue_num, "status:verify", "status:build")
                    # Fall through to VERIFY
                    resume_stage = "verify"

                if resume_stage == "verify":
                    save_checkpoint(issue_num, "verify")
                    verify_pass = run_verify_stage(issue)
                    clear_checkpoint()
                    if verify_pass:
                        transition_label(issue_num, "status:review", "status:verify")
                        log_metrics("pipeline_complete", issue=str(issue_num), result="review")
                    else:
                        transition_label(issue_num, "status:blocked", "status:verify")
                        log_metrics("pipeline_complete", issue=str(issue_num), result="blocked")
                    recovered = None
                    continue

                if resume_stage == "design":
                    # Run the full pipeline from scratch (already rolled back to pre-design)
                    recovered = None
                    run_pipeline(issue)
                    continue

                recovered = None
                continue

            # ── Fetch next ready ticket ──
            issue = fetch_ready_ticket()
            if issue is None:
                print("[ralph] No ready tickets. Sleeping...")
                log_metrics("daemon_idle")
                for _ in range(60):
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
