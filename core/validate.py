#!/usr/bin/env python3
"""
Ralph v3 — Validation Gate

Port of core/ralph_validate.sh to Python.
Exits 0 only when ALL quality checks pass.

Tiers: smoke | targeted | integration | full | e2e | performance
Default: targeted

Policy:
    - e2e and performance tiers are BLOCKED unless RALPH_ALLOW_E2E=1.
    - Lint runs only on modified/untracked files.
    - targeted tier uses detect_affected_tests.py for fast feedback.

Usage:
    ralph validate [--tier=<tier>]
    python core/validate.py --tier=targeted
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
VENV_PATH = Path(os.environ.get("RALPH_VENV_PATH", PROJECT_ROOT / ".venv"))
TEST_DIR = os.environ.get("RALPH_TEST_DIR", "tests")
ALLOW_E2E = os.environ.get("RALPH_ALLOW_E2E", "0") == "1"
DEFAULT_LINT_TOOLS = os.environ.get("RALPH_LINT_TOOLS", "black isort flake8 mypy").split()

# Detect Python
PYTHON_CMD = os.environ.get("RALPH_PYTHON_CMD", "")
if not PYTHON_CMD:
    for candidate in [
        VENV_PATH / "bin" / "python",
        VENV_PATH / "bin" / "python3",
    ]:
        if candidate.exists():
            PYTHON_CMD = str(candidate)
            break
    if not PYTHON_CMD:
        PYTHON_CMD = "python3"

# Detect core directory
CORE_DIR = os.environ.get("RALPH_CORE_DIR",
                          str(Path(__file__).parent.resolve()))

DETECT_SCRIPT = os.path.join(CORE_DIR, "detect_affected_tests.py")

# pytest addopts override
PYTEST_ADOPTS = ["-o", "addopts=--tb=short --strict-markers"]


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run a command, return CompletedProcess."""
    return subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)


def get_modified_py_files() -> list[str]:
    """Return list of modified + untracked .py files."""
    modified = set()
    # Modified tracked files
    result = run(["git", "diff", "--name-only", "--diff-filter=ACM"])
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.endswith(".py"):
            modified.add(line)
    # Untracked files
    result = run(["git", "ls-files", "--others", "--exclude-standard"])
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.endswith(".py"):
            modified.add(line)
    return sorted(modified)


def run_pytest(tier: str) -> int:
    """Run pytest for the given tier. Returns exit code."""
    base = [PYTHON_CMD, "-m", "pytest"] + PYTEST_ADOPTS

    tier_map = {
        "smoke": [
            f"{TEST_DIR}/unit/", "-x", "-q",
            "-m", "unit",
        ],
        "targeted": [
            # Populated dynamically below
        ],
        "integration": [
            f"{TEST_DIR}/integration/", "-q",
            "-m", "integration",
        ],
        "full": [
            f"{TEST_DIR}/", "-q",
            "-m", "not e2e and not performance and not broker_live",
        ],
        "e2e": [
            f"{TEST_DIR}/e2e/", "-v",
        ],
        "performance": [
            f"{TEST_DIR}/performance/", "-v",
        ],
    }

    if tier == "targeted":
        # Use detect_affected_tests.py
        if os.path.exists(DETECT_SCRIPT):
            result = run([PYTHON_CMD, DETECT_SCRIPT], check=False)
            affected = result.stdout.strip()
        else:
            affected = f"{TEST_DIR}/unit/"

        if not affected:
            print("[ralph] No affected tests detected. Skipping pytest.")
            return 0

        cmd = base + affected.split() + [
            "-q", "-m", "not e2e and not performance",
        ]
    elif tier == "targetted":
        # Handle common typo
        return run_pytest("targeted")
    else:
        cmd = base + tier_map.get(tier, [])

    print()
    result = run(cmd, check=False)
    return result.returncode


def run_lint(tool: str, files: list[str]) -> bool:
    """Run a lint tool on the given files. Returns True if passed."""
    print()

    tool_configs = {
        "black": [PYTHON_CMD, "-m", "black", "--check"] + files,
        "isort": [PYTHON_CMD, "-m", "isort", "--check-only"] + files,
        "flake8": [PYTHON_CMD, "-m", "flake8"] + files,
        "ruff": [PYTHON_CMD, "-m", "ruff", "check"] + files,
    }

    if tool == "mypy":
        # Build module names from file paths
        modules = []
        for f in files:
            if f.endswith(".py"):
                if f.endswith("__init__.py"):
                    mod = f.replace("src/", "").replace("/", ".").replace(".__init__.py", "")
                else:
                    mod = f.replace("src/", "").replace("/", ".").replace(".py", "")
                if mod:
                    modules.extend(["-m", mod])
        if not modules:
            print("[ralph] mypy: no modules to check.")
            return True
        cmd = [PYTHON_CMD, "-m", "mypy", "--follow-imports=silent"] + modules
    elif tool in tool_configs:
        cmd = tool_configs[tool]
    else:
        print(f"[ralph] Skipping unknown lint tool: {tool}")
        return True

    result = run(cmd, check=False)
    return result.returncode == 0


# ─────────────────────────────────────────────────────────
# Main validation gate
# ─────────────────────────────────────────────────────────

def validate(tier: str = "targeted") -> int:
    """
    Run the full validation gate.
    Returns 0 on pass, 1 on failure.
    """
    # ── Policy enforcement ──
    if tier in ("e2e", "performance") and not ALLOW_E2E:
        print(f"[ralph] ERROR: {tier} tier is blocked in the Ralph loop.")
        print("[ralph] Targeted-tests-only policy enforced.")
        print("[ralph] Set RALPH_ALLOW_E2E=1 to override (operator-only).")
        return 1

    # ── Activate venv if available ──
    activate = VENV_PATH / "bin" / "activate_this.py"
    if activate.exists():
        # Use activate_this.py for venv activation in-process
        exec(activate.read_text(), {"__file__": str(activate)})

    print("=" * 41)
    print("[ralph] Validation Gate Starting...")
    print(f"[ralph] Test tier: {tier}")
    print(f"[ralph] Python: {PYTHON_CMD}")
    print("=" * 41)

    failed = False
    step = 1
    total_steps = 5

    # ── 1. pytest ──
    label = f"[{step}/{total_steps}]"
    print(f"\n[{step}/{total_steps}] Running {tier.upper()} tests...")

    pytest_exit = run_pytest(tier)

    if pytest_exit == 0:
        print(f"\n{label} pytest {tier} PASSED")
    elif pytest_exit == 5:
        # Exit code 5 = no tests collected (all deselected)
        print(f"\n{label} pytest {tier} PASSED (no tests collected)")
    else:
        print(f"\n{label} pytest {tier} FAILED")
        failed = True
    step += 1

    # ── 2-5. Lint tools (on modified files only) ──
    modified_files = get_modified_py_files()

    if not modified_files:
        print("\n[ralph] No modified/untracked Python files detected.")
        print("[ralph] Skipping lint/formatter checks.")
    else:
        print(f"\n[ralph] Modified/untracked Python files detected:")
        for f in modified_files:
            print(f"  {f}")
        print()

        for tool in DEFAULT_LINT_TOOLS:
            if step > total_steps:
                continue
            print(f"\n[{step}/{total_steps}] Running {tool}...")
            if run_lint(tool, modified_files):
                print(f"\n[{step}/{total_steps}] {tool} PASSED")
            else:
                print(f"\n[{step}/{total_steps}] {tool} FAILED")
                failed = True
            step += 1

    # ── Result ──
    print()
    print("=" * 41)
    if failed:
        print("RALPH_GATE_FAILED")
        print("=" * 41)
        return 1
    else:
        print("RALPH_GATE_PASSED")
        print("=" * 41)
        return 0


# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ralph v3 Validation Gate"
    )
    parser.add_argument(
        "--tier",
        default="targeted",
        choices=["smoke", "targeted", "integration", "full", "e2e", "performance"],
        help="Test tier (default: targeted)",
    )
    args = parser.parse_args()

    # Also support --tier=value from the old bash CLI style
    return validate(args.tier)


if __name__ == "__main__":
    sys.exit(main())
