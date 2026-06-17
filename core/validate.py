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
CONFIG_FILE = PROJECT_ROOT / ".ralph" / "config.toml"


def _load_config() -> dict:
    """Best-effort load of .ralph/config.toml."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        import tomllib  # type: ignore

        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception:
        pass
    try:
        import tomli  # type: ignore

        with open(CONFIG_FILE, "rb") as f:
            return tomli.load(f)
    except Exception:
        pass
    return {}


_CONFIG = _load_config()
_DEFAULT_LINT_TOOLS_FROM_CONFIG = _CONFIG.get("validate", {}).get("lint_tools", [])
DEFAULT_LINT_TOOLS = (
    os.environ.get("RALPH_LINT_TOOLS", "").split()
    or _DEFAULT_LINT_TOOLS_FROM_CONFIG
    or ["black", "isort", "flake8", "mypy"]
)
DEFAULT_TIER = os.environ.get("RALPH_DEFAULT_TIER", "") or _CONFIG.get(
    "validate", {}
).get("default_tier", "targeted")

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
CORE_DIR = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parent.resolve()))

DETECT_SCRIPT = os.path.join(CORE_DIR, "detect_affected_tests.py")

# pytest addopts override
PYTEST_ADOPTS = ["-o", "addopts=--tb=short --strict-markers"]


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────


def run(
    cmd: list[str], check: bool = False, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run a command, return CompletedProcess.

    If the command fails and check is False, emit stdout/stderr so the
    operator can see why the gate failed.
    """
    run_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=PROJECT_ROOT, env=run_env
    )
    if result.returncode != 0 and not check:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    return result


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


def detect_collisions(paths: list[str]) -> dict[str, list[str]]:
    """
    Detect pytest module-name collisions.

    Pytest imports test modules by basename. If two explicit file paths share
    the same basename (e.g. tests/unit/test_cli.py and
    tests/integration/test_cli.py), the second collection fails with an
    import-file mismatch. Return a mapping of colliding basenames to paths.
    """
    from collections import defaultdict

    by_basename: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        by_basename[Path(p).name].append(p)
    return {name: ps for name, ps in by_basename.items() if len(ps) > 1}


def run_pytest_invocation(cmd: list[str], env: dict[str, str] | None = None) -> int:
    """Run a single pytest invocation. Returns exit code."""
    print(f"[ralph] pytest invocation: {' '.join(cmd)}")
    result = run(cmd, check=False, env=env)
    return result.returncode


def run_pytest_split_by_directory(
    base: list[str],
    paths: list[str],
    suffix: list[str],
    env: dict[str, str] | None = None,
) -> int:
    """
    Split pytest paths by parent directory and run one invocation per directory.
    Returns the worst (highest) exit code across all invocations.
    """
    from collections import defaultdict

    by_dir: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        by_dir[str(Path(p).parent)].append(p)

    max_exit = 0
    for dir_path in sorted(by_dir):
        dir_paths = sorted(by_dir[dir_path])
        cmd = base + dir_paths + suffix
        exit_code = run_pytest_invocation(cmd, env=env)
        if exit_code > max_exit:
            max_exit = exit_code
    return max_exit


def run_pytest(tier: str, pytest_paths: list[str] | None = None) -> int:
    """Run pytest for the given tier or on explicit paths. Returns exit code."""
    base = [PYTHON_CMD, "-m", "pytest"] + PYTEST_ADOPTS

    if pytest_paths:
        paths = pytest_paths
        suffix = ["-q", "-m", "not e2e and not performance and not broker_live"]
        env = {"RALPH_NO_RECURSIVE_PYTEST": "1"}
        print(f"[ralph] Running specified tests: {paths}")
    elif tier == "targeted":
        # Use detect_affected_tests.py
        if os.path.exists(DETECT_SCRIPT):
            result = run([PYTHON_CMD, DETECT_SCRIPT], check=False)
            affected = result.stdout.strip()
        else:
            affected = f"{TEST_DIR}/unit/"

        if not affected:
            print("[ralph] No affected tests detected. Skipping pytest.")
            return 0

        paths = affected.split()
        suffix = ["-q", "-m", "not e2e and not performance"]
        env = {"RALPH_NO_RECURSIVE_PYTEST": "1"}
    elif tier == "targetted":
        # Handle common typo
        return run_pytest("targeted")
    else:
        tier_map = {
            "smoke": [
                f"{TEST_DIR}/unit/",
                "-x",
                "-q",
                "-m",
                "unit",
            ],
            "integration": [
                f"{TEST_DIR}/integration/",
                "-q",
                "-m",
                "integration",
            ],
            "full": [
                f"{TEST_DIR}/",
                "-q",
                "-m",
                "not e2e and not performance and not broker_live",
            ],
            "e2e": [
                f"{TEST_DIR}/e2e/",
                "-v",
            ],
            "performance": [
                f"{TEST_DIR}/performance/",
                "-v",
            ],
        }
        cmd = base + tier_map.get(tier, [])
        print()
        # Prevent target-project tests that spawn pytest from recursing forever.
        result = run(cmd, check=False, env={"RALPH_NO_RECURSIVE_PYTEST": "1"})
        return result.returncode

    # Check for module basename collisions and split by directory if needed.
    collisions = detect_collisions(paths)
    if collisions:
        print("[ralph] WARNING: detected test module basename collisions:")
        for name, colliding_paths in sorted(collisions.items()):
            print(f"  - {name}: {', '.join(colliding_paths)}")
        print(
            "[ralph] Splitting pytest into separate invocations per directory "
            "to avoid import conflicts."
        )
        return run_pytest_split_by_directory(base, paths, suffix, env=env)

    cmd = base + paths + suffix
    return run_pytest_invocation(cmd, env=env)


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
                    mod = (
                        f.replace("src/", "")
                        .replace("/", ".")
                        .replace(".__init__.py", "")
                    )
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


def validate(tier: str = DEFAULT_TIER, pytest_paths: list[str] | None = None) -> int:
    """
    Run the full validation gate.
    Returns 0 on pass, 1 on failure.
    """
    # Normalize empty list to None
    if not pytest_paths:
        pytest_paths = None
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

    pytest_exit = run_pytest(tier, pytest_paths=pytest_paths)

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
        print("\n[ralph] Modified/untracked Python files detected:")
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
    parser = argparse.ArgumentParser(description="Ralph v3 Validation Gate")
    parser.add_argument(
        "--tier",
        default="targeted",
        choices=["smoke", "targeted", "integration", "full", "e2e", "performance"],
        help="Test tier (default: targeted)",
    )
    parser.add_argument(
        "--pytest-paths",
        nargs="*",
        default=None,
        help="Run pytest on these specific test paths only",
    )
    args = parser.parse_args()

    # Also support --tier=value from the old bash CLI style
    return validate(args.tier, pytest_paths=args.pytest_paths)


if __name__ == "__main__":
    sys.exit(main())
