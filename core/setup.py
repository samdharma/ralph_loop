#!/usr/bin/env python3
"""
Ralph v3 — Setup

Post-clone environment check. Verifies all prerequisites and creates
local directories. Run once after `git clone`.

Usage:
    ralph setup
"""

import os
import subprocess
import sys
from pathlib import Path

import project_sync

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))

CHECKS: list = []


def ok(msg: str):
    print(f"  \033[32m✓\033[0m {msg}")


def warn(msg: str):
    print(f"  \033[33m⚠\033[0m  {msg}")


def fail(msg: str):
    print(f"  \033[31m✗\033[0m {msg}")


def check(desc: str, fn) -> bool:
    """Run a check, print result, return pass/fail."""
    try:
        result, detail = fn()
        if result:
            ok(f"{desc} ({detail})" if detail else desc)
            return True
        else:
            fail(f"{desc} — {detail}")
            return False
    except Exception as e:
        fail(f"{desc} — {e}")
        return False


# ─────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────


def check_gh_auth():
    """Verify GitHub CLI is authenticated."""
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if result.returncode == 0:
        return True, "authenticated"
    return False, "run: gh auth login"


def check_git_remote():
    """Verify we're in a git repo with a remote."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    if result.returncode == 0:
        return True, result.stdout.strip()
    return False, "no origin remote"


def check_python():
    """Verify Python 3.10+ is available."""
    result = subprocess.run(
        [sys.executable, "--version"], capture_output=True, text=True
    )
    ver_str = result.stdout.strip()
    # Parse "Python 3.x.y"
    parts = ver_str.split()
    if len(parts) >= 2:
        ver = parts[1]
        major, minor = ver.split(".")[:2]
        if int(major) >= 3 and int(minor) >= 10:
            return True, ver_str
        return False, f"need 3.10+, got {ver_str}"
    return False, f"unexpected version output: {ver_str}"


def check_agent():
    """Verify at least one AI agent is available."""
    for agent in ["pi", "kimi"]:
        result = subprocess.run(["which", agent], capture_output=True, text=True)
        if result.returncode == 0:
            return True, agent
    return False, "install pi or kimi"


def check_pi_subagent():
    """Verify pi-subagent extension is installed (required for Phase 3 sub-agents)."""
    # First check if pi is available
    pi_result = subprocess.run(["which", "pi"], capture_output=True, text=True)
    if pi_result.returncode != 0:
        return True, "pi not installed (skipped)"

    # Check if the subagent extension is installed
    result = subprocess.run(["pi", "extension", "list"], capture_output=True, text=True)
    if "pi-subagent" in result.stdout or "@mjakl/pi-subagent" in result.stdout:
        return True, "pi-subagent installed"

    # Extension not found — warn but don't fail (engine falls back to pi --print)
    return True, "pi-subagent not installed (falls back to pi --print for sub-agents)"


def check_gh_repo_access():
    """Verify gh can list issues for this repo."""
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        ).stdout.strip()

        # Extract owner/repo from remote URL
        repo = None
        for prefix in ["https://github.com/", "git@github.com:"]:
            if remote.startswith(prefix):
                path = remote[len(prefix) :]
                if path.endswith(".git"):
                    path = path[:-4]
                repo = path
                break

        if not repo:
            return False, "cannot parse repo from remote"

        result = subprocess.run(
            ["gh", "issue", "list", "--repo", repo, "--limit", "1"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, repo
        return False, f"cannot access {repo}"
    except Exception as e:
        return False, str(e)


def check_gh_labels():
    """Verify required labels exist in the repo."""
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        ).stdout.strip()

        repo = None
        for prefix in ["https://github.com/", "git@github.com:"]:
            if remote.startswith(prefix):
                path = remote[len(prefix) :]
                if path.endswith(".git"):
                    path = path[:-4]
                repo = path
                break

        if not repo:
            return False, "cannot parse repo from remote"

        result = subprocess.run(
            ["gh", "label", "list", "--repo", repo, "--json", "name"],
            capture_output=True,
            text=True,
        )
        import json

        labels = [item["name"] for item in json.loads(result.stdout)]

        required = [
            "status:ready",
            "status:design",
            "status:build",
            "status:build-retry",
            "status:verify",
            "status:verify-retry",
            "status:review",
            "status:blocked",
        ]
        missing = [label for label in required if label not in labels]

        if not missing:
            return True, "all required labels present"
        return (
            False,
            f"missing: {', '.join(missing)} (run 'ralph init --create-labels' to auto-create)",
        )
    except Exception as e:
        return False, str(e)


def check_project_sync():
    """Verify GitHub Project board sync if a project is configured."""
    if not project_sync.project_enabled():
        return (
            True,
            "board sync disabled (set ticket.project in .ralph/config.toml or run 'ralph init' again)",
        )
    ok, detail = project_sync.check_project_access()
    if ok:
        return True, f"board sync enabled — {detail}"
    return (
        True,
        f"board sync enabled but {detail} (sync will warn but not block the pipeline)",
    )


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────


def main() -> int:
    print("╔══════════════════════════════════════════╗")
    print("║   Ralph v3 — Setup                       ║")
    print("╚══════════════════════════════════════════╝")
    print()
    print(f"Project: {PROJECT_ROOT}")
    print()

    all_pass = True
    all_pass &= check("GitHub CLI authenticated", check_gh_auth)
    all_pass &= check("Git remote", check_git_remote)
    all_pass &= check("Python 3.10+", check_python)
    all_pass &= check("AI agent (pi/kimi)", check_agent)
    all_pass &= check("pi-subagent extension", check_pi_subagent)
    all_pass &= check("GitHub repo access", check_gh_repo_access)
    all_pass &= check("Required labels", check_gh_labels)
    check("GitHub Project board sync", check_project_sync)

    print()

    # ── Create local directories ──
    for d in ["logs", ".ralph"]:
        dp = PROJECT_ROOT / d
        if not dp.exists():
            dp.mkdir(parents=True, exist_ok=True)
            ok(f"Created {d}/")
        else:
            ok(f"{d}/ exists")

    print()

    if all_pass:
        print("Setup complete! Run 'ralph daemon' to start building.")
        return 0
    else:
        print("Some checks failed. Fix the issues above and re-run 'ralph setup'.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
