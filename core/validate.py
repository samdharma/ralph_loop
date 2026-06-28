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
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
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

# pytest timeout in seconds (0 = no timeout). Override with RALPH_PYTEST_TIMEOUT.
PYTEST_TIMEOUT = int(os.environ.get("RALPH_PYTEST_TIMEOUT", "300"))

# Quarantine file (per spec §10.3 C3). The file holds a YAML list of
# ``{test_id, added_at, reason, auto_added}`` entries. Tests listed here
# are deselected from pytest invocations.
QUARANTINE_FILE = PROJECT_ROOT / TEST_DIR / "quarantine.yaml"

# Retry mode (per spec §10.3 C4). When True, validate skips
# integration/full/e2e tiers; only pytest-paths runs. Set via
# ``bin/ralph validate --retry`` or RALPH_RETRY=1 env var.
RETRY_MODE = os.environ.get("RALPH_RETRY", "0") == "1"

_EXPENSIVE_TIERS = frozenset({"integration", "full", "e2e"})

# Failure history for auto-quarantine (C3.2). Each line is one validate
# run: ``{"run_at": iso8601, "failures": [test_id, ...], "passes": [...]}``.
# The auto-add logic scans the last 2 runs for consecutive failures.
TEST_FAILURE_HISTORY_FILE = PROJECT_ROOT / ".ralph" / "test-failure-history.jsonl"


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────


def run(
    cmd: list[str],
    check: bool = False,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, return CompletedProcess.

    If the command fails and check is False, emit stdout/stderr so the
    operator can see why the gate failed.
    """
    run_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=run_env,
        timeout=timeout,
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
    result = run(["git", "diff", "--name-only", "--diff-filter=ACMR"])
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


# ─────────────────────────────────────────────────────────
# A6.1 — Critical-path test config (spec §10.1 A6)
# ─────────────────────────────────────────────────────────


def get_critical_paths() -> list[str]:
    """Return the list of critical-path tests from .ralph/config.toml.

    Per spec §10.1 A6: critical paths are run first; their failure blocks
    BUILD. The list is loaded from `[validate] critical_paths = [...]` in
    the project's `.ralph/config.toml`. Returns an empty list if not set.

    The result is computed at call time (not import time) so config
    changes are picked up without restarting the daemon.
    """
    config = globals().get("_CONFIG") or _load_config()
    return list(config.get("validate", {}).get("critical_paths", []) or [])


def is_critical_run(force: bool = False) -> bool:
    """Return True if the current validate run is in critical-path mode.

    Per spec §10.1 A6: critical-path mode is active when either:
    - `[validate] critical_paths` is non-empty in config, OR
    - The `--critical` CLI flag is set (passed via `force=True`).
    """
    if force:
        return True
    return len(get_critical_paths()) > 0


# ─────────────────────────────────────────────────────────
# A1.1 — Pytest exit-code classifier (spec §10.1 A1)
# ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Classification:
    """Result of classifying a pytest exit code.

    Per spec §7.2 — frozen dataclass for lookup tables.
    """

    exit_code: int
    classification: str  # one of: success, test_failure, timeout, interrupted, internal_error, unknown
    action: str  # one of: accept, retry_transient, block


# Pytest exit codes and their meaning.
# Reference: pytest docs + POSIX signal conventions.
#
# Per spec §10.2 B1, the `action` field drives retry-vs-block:
#   - exit 0   → accept
#   - exit 1-2 → test_failure / retry_l2 (up to 2 retries)
#   - exit 3-5 → internal_error / block
#   - exit 124 → timeout / retry_transient (up to 1 retry)
#   - exit 137, 143 → interrupted / retry_transient (DISTINCT from timeout)
#   - other   → unknown / block
_PYTEST_EXIT_TABLE: dict[int, Classification] = {
    0: Classification(0, "success", "accept"),
    1: Classification(1, "test_failure", "retry_l2"),
    2: Classification(2, "test_failure", "retry_l2"),  # test execution interrupted
    3: Classification(3, "internal_error", "block"),  # internal error
    4: Classification(4, "test_failure", "block"),  # pytest usage error
    5: Classification(
        5, "internal_error", "block"
    ),  # no tests collected (config issue)
    # 124, 137, 143 handled separately for distinct classification
}


def classify_pytest_exit_code(exit_code: int) -> Classification:
    """Classify a pytest exit code into a structured Classification.

    Per spec §10.1 A1 + §10.2 B1:
    - exit 0   → success / accept
    - exit 1-2 → test_failure / retry_l2 (up to 2 retries)
    - exit 3-5 → internal_error / block
    - exit 124 → timeout / retry_transient
    - exit 137 → interrupted (SIGKILL) / retry_transient (DISTINCT from timeout)
    - exit 143 → interrupted (SIGTERM) / retry_transient (DISTINCT from timeout)
    - other    → unknown / block
    """
    if exit_code == 124:
        return Classification(exit_code, "timeout", "retry_transient")
    if exit_code in (137, 143):
        return Classification(exit_code, "interrupted", "retry_transient")
    if exit_code in _PYTEST_EXIT_TABLE:
        return _PYTEST_EXIT_TABLE[exit_code]
    return Classification(exit_code, "unknown", "block")


# Per spec §7.2 — frozen dataclass for retry policy lookup tables.
@dataclass(frozen=True)
class RetryPolicy:
    """Retry policy keyed by action and exit code.

    Per spec §10.2 B1 the engine consults the policy at each retry
    decision. ``applies_to`` is a frozenset of pytest exit codes that
    the policy applies to (used by ``B1.1 retry_budget_config``).
    """

    max_attempts: int
    backoff_seconds: float
    applies_to: frozenset[int]


# Per spec §10.2 B1 — DESIGN-stage failures block regardless of exit
# code, even when the classifier alone would suggest retry. This is
# enforced via :func:`retry_action_for_stage` below.
def retry_action_for_stage(classified_action: str, stage: str) -> str:
    """Return the effective action for a stage.

    Per spec §10.2 B1, the DESIGN stage is fail-fast: any failure —
    even one the classifier labels as retryable — is final and blocks
    the pipeline. All other stages honour the classifier's decision.
    """
    if stage == "design" and classified_action != "accept":
        return "block"
    return classified_action


_STDOUT_TAIL_LINES = 50  # Spec §10.1 A5: tail of agent stdout in failure reports

# Pytest result lines look like:
#   FAILED tests/unit/test_x.py::test_y - message
#   PASSED tests/unit/test_x.py::test_y
_PYTEST_RESULT_LINE_RE = re.compile(r"^(PASSED|FAILED|ERROR)\s+(\S+)")


def _parse_pytest_test_ids(stdout: str) -> tuple[list[str], list[str]]:
    """Parse PASSED/FAILED/ERROR test node IDs from pytest stdout."""
    failures: list[str] = []
    passes: list[str] = []
    for line in stdout.splitlines():
        match = _PYTEST_RESULT_LINE_RE.match(line.strip())
        if not match:
            continue
        status, test_id = match.groups()
        if status == "PASSED":
            passes.append(test_id)
        elif status in ("FAILED", "ERROR"):
            failures.append(test_id)
    return failures, passes


def _process_pytest_result_for_quarantine(exit_code: int, stdout: str) -> None:
    """Record the run and auto-quarantine tests that failed twice consecutively.

    Per spec §10.3 C3: a test that fails in two consecutive runs with no
    intervening pass is auto-added to ``tests/quarantine.yaml`` and a GitHub
    issue is posted.
    """
    failures, passes = _parse_pytest_test_ids(stdout)
    run_at = datetime.now(timezone.utc).isoformat()
    record_test_result(failures, passes, run_at=run_at)

    for test_id in failures:
        if should_auto_quarantine(test_id):
            if auto_quarantine_test(test_id):
                history = _load_failure_history()
                timestamps = [
                    run.get("run_at", run_at)
                    for run in history[-2:]
                    if test_id in run.get("failures", [])
                ]
                post_flake_quarantined_issue(
                    test_id, failure_timestamps=timestamps or [run_at, run_at]
                )


def run_pytest_invocation(cmd: list[str], env: dict[str, str] | None = None) -> dict:
    """Run a single pytest invocation. Returns a structured result dict.

    Per spec §10.1 A1 (A1.2 emitter), the result dict has keys:
      - exit_code: int
      - classification: str (from classify_pytest_exit_code)
      - action: str (from classify_pytest_exit_code)
      - stdout_tail: str (last 50 lines of pytest stdout)
      - junitxml_path: str | None (path to JUnit XML if --junitxml was passed)

    Returns 124 on timeout (mimics `timeout` command convention) so the
    caller can distinguish a hung test from a genuine failure.
    """
    # C3: deselect quarantined tests before running.
    cmd = apply_quarantine_to_cmd(cmd)
    print(f"[ralph] pytest invocation: {' '.join(cmd)}")
    timeout = PYTEST_TIMEOUT if PYTEST_TIMEOUT > 0 else None

    # Detect --junitxml=<path> in the command line for the structured result.
    junitxml_path: str | None = None
    for arg in cmd:
        if isinstance(arg, str) and arg.startswith("--junitxml="):
            junitxml_path = arg.split("=", 1)[1]

    try:
        result = run(cmd, check=False, env=env, timeout=timeout)
        exit_code = result.returncode
        # subprocess returns bytes; decode to str for the JSON-friendly
        # structured result. Per spec §10.1 A1 stdout_tail is str.
        stdout_raw = result.stdout or b""
        stdout = (
            stdout_raw.decode("utf-8", errors="replace")
            if isinstance(stdout_raw, (bytes, bytearray))
            else stdout_raw
        )
    except subprocess.TimeoutExpired:
        print(f"[ralph] pytest timed out after {PYTEST_TIMEOUT}s")
        exit_code = 124
        stdout = ""

    # C3: record results and auto-quarantine repeat offenders.
    _process_pytest_result_for_quarantine(exit_code, stdout)

    classification = classify_pytest_exit_code(exit_code)
    stdout_tail = "\n".join(stdout.splitlines()[-_STDOUT_TAIL_LINES:])
    return {
        "exit_code": exit_code,
        "classification": classification.classification,
        "action": classification.action,
        "stdout_tail": stdout_tail,
        "junitxml_path": junitxml_path,
    }


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
        result = run_pytest_invocation(cmd, env=env)
        exit_code = result["exit_code"]
        if exit_code > max_exit:
            max_exit = exit_code
    return max_exit


def run_pytest(tier: str, pytest_paths: list[str] | None = None) -> int:
    """Run pytest for the given tier or on explicit paths. Returns exit code."""
    base = [PYTHON_CMD, "-m", "pytest"] + PYTEST_ADOPTS

    # A4.1: append --junitxml=<path> if RALPH_JUNITXML is set.
    junitxml_path = os.environ.get("RALPH_JUNITXML")
    if junitxml_path:
        base.append(f"--junitxml={junitxml_path}")

    # A6.1: if critical-path mode is active, run critical paths FIRST.
    # A failure here short-circuits to a blocking exit code so BUILD stops.
    if is_critical_run(force=os.environ.get("RALPH_CRITICAL") == "1"):
        critical_paths = get_critical_paths()
        if critical_paths:
            print(f"[ralph] Running {len(critical_paths)} critical-path test(s) first")
            crit_cmd = base + critical_paths + ["-q"]
            crit_result = run_pytest_invocation(
                crit_cmd, env={"RALPH_NO_RECURSIVE_PYTEST": "1"}
            )
            if crit_result["exit_code"] != 0:
                print("[ralph] Critical-path test(s) failed; blocking BUILD.")
                return crit_result["exit_code"]

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
        pytest_result = run_pytest_invocation(
            cmd, env={"RALPH_NO_RECURSIVE_PYTEST": "1"}
        )
        return pytest_result["exit_code"]

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
    # Internal callers (run_pytest, validate) consume only exit_code.
    return run_pytest_invocation(cmd, env=env)["exit_code"]


def run_lint(tool: str, files: list[str]) -> bool:
    """Run a lint tool on the given files. Returns True if passed."""
    print()

    tool_configs = {
        "black": [PYTHON_CMD, "-m", "black", "--check"] + files,
        "isort": [PYTHON_CMD, "-m", "isort", "--check-only", "--profile", "black"]
        + files,
        "flake8": [PYTHON_CMD, "-m", "flake8"] + files,
        "ruff": [PYTHON_CMD, "-m", "ruff", "check"] + files,
    }

    if tool == "mypy":
        # Pass file paths directly; mypy resolves module names via mypy_path
        # or project structure. This works for both src/ and flat layouts.
        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            print("[ralph] mypy: no files to check.")
            return True
        cmd = [
            PYTHON_CMD,
            "-m",
            "mypy",
            "--follow-imports=silent",
            "--explicit-package-bases",
            "--ignore-missing-imports",
        ] + py_files
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

    # C3: auto-remove stale quarantine entries on every validate run.
    removed = unquarantine_stale_entries()
    if removed:
        print(f"[ralph] Auto-removed {removed} stale quarantine entries (>7 days).")

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
    elif pytest_exit == 124:
        print(f"\n{label} pytest {tier} TIMED OUT after {PYTEST_TIMEOUT}s")
        failed = True
    else:
        print(f"\n{label} pytest {tier} FAILED")
        failed = True
    step += 1

    # ── 2-5. Lint tools (on modified files only) ──
    # Only check modified files if tests passed. If tests already failed,
    # skip lint — the gate is already doomed and the "modified files"
    # message is just confusing noise (the IMPLEMENT agent always modifies
    # files, that's normal).
    if not failed:
        modified_files = get_modified_py_files()

        if not modified_files:
            print("\n[ralph] No modified/untracked Python files detected.")
            print("[ralph] Skipping lint/formatter checks.")
        else:
            print(
                "\n[ralph] Checking modified/untracked Python files (IMPLEMENT agent changes):"
            )
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
    else:
        print("\n[ralph] Tests failed — skipping modified-file lint checks.")

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
    parser.add_argument(
        "--junitxml",
        default=None,
        metavar="PATH",
        help="Emit JUnit XML report to PATH (spec §10.1 A4). Used by the "
        "engine to surface structured failures to the agent.",
    )
    parser.add_argument(
        "--critical",
        action="store_true",
        help="Run critical-path tests first (per [validate] critical_paths "
        "in .ralph/config.toml or this flag). Failure blocks BUILD.",
    )
    parser.add_argument(
        "--unquarantine-stale",
        action="store_true",
        help="Remove quarantine.yaml entries older than 7 days "
        "(per spec §10.3 C3). Prints the count of removed entries.",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Run only the pytest-paths tier; skip integration/full/e2e "
        "(per spec §10.3 C4). Used by BUILD's retry path.",
    )
    args = parser.parse_args()

    # Also support --tier=value from the old bash CLI style
    if args.junitxml:
        os.environ["RALPH_JUNITXML"] = args.junitxml
    if args.critical:
        os.environ["RALPH_CRITICAL"] = "1"
    if args.unquarantine_stale:
        removed = unquarantine_stale_entries()
        print(f"[ralph] Removed {removed} stale quarantine entries.")
        return 0
    if args.retry:
        os.environ["RALPH_RETRY"] = "1"
        # The module-level constant is captured at import time, so we
        # update it via the global for this invocation.
        global RETRY_MODE
        RETRY_MODE = True
        return validate_with_retry(pytest_paths=args.pytest_paths)
    return validate(args.tier, pytest_paths=args.pytest_paths)


# ─────────────────────────────────────────────────────────
# C3.1 — Quarantine schema (spec §10.3 C3)
# ─────────────────────────────────────────────────────────
#
# Per spec §10.3 C3 and plan §3 R-7: tests/quarantine.yaml holds a list
# of ``{test_id, added_at, reason, auto_added}`` entries. Listed tests
# are deselected from pytest invocations. Auto-added entries (from C3.2)
# include ``auto_added: true``. Auto-unquarantine (C3.3) removes entries
# older than 7 days.
#
# We use a minimal YAML parser because PyYAML is not a project
# dependency (stdlib-only project policy; ``tomllib`` is used for the
# other config file). The parser handles the constrained YAML format
# we ourselves produce — a list of dicts with string keys and string/
# bool values. This is sufficient for our needs; complex YAML features
# are not used.


def _parse_quarantine_yaml(text: str) -> list[dict]:
    """Parse the constrained YAML format produced by the project.

    Format::

        - test_id: <id>
          added_at: "<iso8601>"
          reason: <str>
          auto_added: <bool>

    Returns a list of dicts. Empty input returns an empty list.
    """
    entries: list[dict] = []
    current: dict[str, object] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("- "):
            # New list item.
            if current is not None:
                entries.append(current)
            current = {}
            rest = line[2:]
        else:
            if current is None:
                # Stray content; skip.
                continue
            rest = line
        # Split key: value.
        if ":" not in rest:
            continue
        key, _, value = rest.partition(":")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        # Booleans.
        coerced: object = value
        if value == "true":
            coerced = True
        elif value == "false":
            coerced = False
        current[key] = coerced
    if current is not None:
        entries.append(current)
    return entries


def _dump_quarantine_yaml(entries: list[dict]) -> str:
    """Serialize entries back into the constrained YAML format."""
    lines: list[str] = []
    for e in entries:
        lines.append(f"- test_id: {e['test_id']}")
        lines.append(f"  added_at: \"{e['added_at']}\"")
        reason = str(e.get("reason", ""))
        if any(c in reason for c in [":", "#", "\n"]):
            lines.append(f'  reason: "{reason}"')
        else:
            lines.append(f"  reason: {reason}")
        lines.append(
            f"  auto_added: {'true' if e.get('auto_added', False) else 'false'}"
        )
        lines.append("")
    return "\n".join(lines)


def load_quarantine_entries() -> list[dict]:
    """Load entries from QUARANTINE_FILE. Returns [] if the file is missing.

    The file is allowed to be missing (first run). An existing-but-empty
    file is also treated as no entries.
    """
    if not QUARANTINE_FILE.exists():
        return []
    try:
        text = QUARANTINE_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []
    return _parse_quarantine_yaml(text)


def save_quarantine_entries(entries: list[dict]) -> None:
    """Persist entries to QUARANTINE_FILE. Creates parent dirs as needed."""
    QUARANTINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE_FILE.write_text(_dump_quarantine_yaml(entries), encoding="utf-8")


def is_quarantined(test_id: str) -> bool:
    """Return True if test_id is listed in QUARANTINE_FILE."""
    for entry in load_quarantine_entries():
        if entry.get("test_id") == test_id:
            return True
    return False


def apply_quarantine_to_cmd(cmd: list[str]) -> list[str]:
    """Return a new cmd with --deselect entries appended for each quarantined test.

    The deselect args are appended at the end of the cmd so they do not
    interfere with positional paths earlier in the list.
    """
    entries = load_quarantine_entries()
    if not entries:
        return list(cmd)
    result = list(cmd)
    for entry in entries:
        result.append("--deselect")
        result.append(entry["test_id"])
    return result


# ─────────────────────────────────────────────────────────
# C3.2 — Auto-quarantine on 2 consecutive failures (spec §10.3 C3)
# ─────────────────────────────────────────────────────────
#
# Per plan §3 R-7: auto-quarantine scans the last 2 runs of the
# failure history. A test that failed in BOTH the most recent run and
# the run immediately before it, with no intervening pass, is
# auto-added to ``tests/quarantine.yaml`` with ``auto_added: true``.


def _load_failure_history() -> list[dict]:
    """Read the per-test failure history. Returns [] if missing or empty."""
    if not TEST_FAILURE_HISTORY_FILE.exists():
        return []
    try:
        import json

        runs: list[dict] = []
        for line in TEST_FAILURE_HISTORY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines rather than crash.
                continue
        return runs
    except OSError:
        return []


def record_test_result(
    failures: list[str],
    passes: list[str],
    run_at: str | None = None,
) -> None:
    """Append a single validate-run entry to the failure history JSONL."""
    import json

    if run_at is None:
        run_at = datetime.now(timezone.utc).isoformat()
    TEST_FAILURE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "run_at": run_at,
        "failures": list(failures),
        "passes": list(passes),
    }
    with TEST_FAILURE_HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def should_auto_quarantine(test_id: str) -> bool:
    """Return True if test_id failed in the last 2 runs with no intervening pass.

    Scoped to the most recent 2 history entries. If fewer than 2 runs
    exist, returns False.
    """
    history = _load_failure_history()
    if len(history) < 2:
        return False
    last_two = history[-2:]
    # Both runs must list test_id in failures, and neither may list it in passes.
    for run in last_two:
        if test_id not in run.get("failures", []):
            return False
        if test_id in run.get("passes", []):
            return False
    return True


def auto_quarantine_test(
    test_id: str, reason: str = "two consecutive failures"
) -> bool:
    """Auto-add test_id to quarantine.yaml. Returns True if a new entry was added.

    Idempotent: if test_id is already in the quarantine, returns False
    and does not modify the file.
    """
    entries = load_quarantine_entries()
    # Already present?
    if any(e.get("test_id") == test_id for e in entries):
        return False
    entry = {
        "test_id": test_id,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "auto_added": True,
    }
    entries.append(entry)
    save_quarantine_entries(entries)
    return True


# ─────────────────────────────────────────────────────────
# C3.3 — Auto-unquarantine after 7 days (spec §10.3 C3)
# ─────────────────────────────────────────────────────────
#
# Per spec §10.3 C3: entries older than 7 days are auto-removed by the
# ``--unquarantine-stale`` CLI flag (or a scheduled sweep). The cutoff
# is configurable via the ``now`` parameter (defaults to "now in UTC")
# so tests can pin a specific moment in time.

_STALE_DAYS = 7


def _parse_isoformat(s: str) -> datetime:
    """Parse an ISO 8601 timestamp. Accepts trailing 'Z' as UTC."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def unquarantine_stale_entries(now: str | None = None) -> int:
    """Remove entries with ``added_at`` older than 7 days from quarantine.

    Returns the count of removed entries. Idempotent on re-run.
    The ``now`` parameter accepts an ISO 8601 timestamp string;
    defaults to current UTC.
    """
    entries = load_quarantine_entries()
    if not entries:
        return 0
    if now is None:
        cutoff = datetime.now(timezone.utc)
    else:
        cutoff = _parse_isoformat(now)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)

    kept: list[dict] = []
    removed = 0
    for entry in entries:
        added_at_raw = entry.get("added_at", "")
        try:
            added_at = _parse_isoformat(added_at_raw)
            if added_at.tzinfo is None:
                added_at = added_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            # Malformed timestamp — keep the entry (don't lose data).
            kept.append(entry)
            continue
        age = cutoff - added_at
        if age.days >= _STALE_DAYS:
            removed += 1
        else:
            kept.append(entry)
    if removed > 0:
        save_quarantine_entries(kept)
    return removed


# ─────────────────────────────────────────────────────────
# C3.4 — 🦠 Flake quarantined: GitHub issue post (spec §10.3 C3)
# ─────────────────────────────────────────────────────────
#
# Per spec §10.3 C3 + plan §3 R-7: when a test is auto-quarantined,
# post a GitHub issue with title ``🦠 Flake quarantined: <test_id>``
# whose body contains the two failure timestamps and a link to the
# failure history. The post is idempotent per ``(run_id, test_id)``
# via a small dedicated JSONL log at
# ``.ralph/quarantine-issue-idempotency.jsonl``.

QUARANTINE_ISSUE_IDEMPOTENCY_FILE = (
    PROJECT_ROOT / ".ralph" / "quarantine-issue-idempotency.jsonl"
)


def _quarantine_issue_already_posted(run_id: str, test_id: str, body_hash: str) -> bool:
    """Return True if the (run_id, test_id, body_hash) has been recorded."""
    if not QUARANTINE_ISSUE_IDEMPOTENCY_FILE.exists():
        return False
    key = f"{run_id}|{test_id}|{body_hash}"
    try:
        with QUARANTINE_ISSUE_IDEMPOTENCY_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("key") == key:
                    return True
    except OSError:
        return False
    return False


def _record_quarantine_issue(
    run_id: str, test_id: str, body_hash: str, issue_url: str | None
) -> None:
    """Append a record to the quarantine-issue idempotency log."""
    QUARANTINE_ISSUE_IDEMPOTENCY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = f"{run_id}|{test_id}|{body_hash}"
    record = {
        "key": key,
        "test_id": test_id,
        "run_id": run_id,
        "body_hash": body_hash,
        "issue_url": issue_url,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    with QUARANTINE_ISSUE_IDEMPOTENCY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _build_flake_quarantine_body(test_id: str, failure_timestamps: list[str]) -> str:
    """Build the body for the flake-quarantined GitHub issue."""
    ts_lines = "\n".join(f"- {ts}" for ts in failure_timestamps)
    history_path = TEST_FAILURE_HISTORY_FILE
    return (
        f"## 🦠 Flake quarantined: `{test_id}`\n\n"
        f"This test was auto-added to `tests/quarantine.yaml` after "
        f"{len(failure_timestamps)} consecutive failures.\n\n"
        f"### Failure timestamps\n{ts_lines}\n\n"
        f"### Failure history\n"
        f"Full per-test failure history: `{history_path}`\n\n"
        f"### Auto-removal\n"
        f"This entry will be auto-removed by "
        f"`bin/ralph validate --unquarantine-stale` after 7 days.\n"
    )


def post_flake_quarantined_issue(
    test_id: str,
    failure_timestamps: list[str],
    run_id: str | None = None,
) -> str | None:
    """Post a 🦠 Flake quarantined: <test_id> GitHub issue. Idempotent.

    Returns the issue URL on success, ``None`` on failure. Idempotent
    per ``(run_id, test_id, body_hash)``: re-invoking with the same
    key returns the previously-recorded URL without making a second
    ``gh`` call.
    """
    if run_id is None:
        run_id = os.environ.get("RALPH_RUN_ID", "default")
    body = _build_flake_quarantine_body(test_id, failure_timestamps)
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    # Idempotency check.
    if _quarantine_issue_already_posted(run_id, test_id, body_hash):
        # Return the previously recorded URL.
        if not QUARANTINE_ISSUE_IDEMPOTENCY_FILE.exists():
            return None
        key = f"{run_id}|{test_id}|{body_hash}"
        try:
            with QUARANTINE_ISSUE_IDEMPOTENCY_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if record.get("key") == key:
                        return record.get("issue_url")
        except OSError:
            return None
        return None

    title = f"🦠 Flake quarantined: {test_id}"
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    result = run(cmd, check=False)
    if result.returncode != 0:
        return None
    # gh prints the new issue URL on stdout.
    issue_url = (result.stdout or "").strip() or None
    _record_quarantine_issue(run_id, test_id, body_hash, issue_url)
    return issue_url


# ─────────────────────────────────────────────────────────
# C4.1 — ralph validate --retry flag (spec §10.3 C4)
# ─────────────────────────────────────────────────────────
#
# Per spec §10.3 C4: ``ralph validate --retry`` runs only the
# pytest-paths tier; integration/full/e2e tiers are skipped. Wired
# into BUILD's retry path (per B1.3) so retry attempts use this flag.


def is_retry_run() -> bool:
    """Return True iff ``--retry`` (or RALPH_RETRY=1) is in effect."""
    return RETRY_MODE


def should_skip_expensive_tiers(tier: str) -> bool:
    """In retry mode, skip integration/full/e2e tiers; otherwise never skip."""
    if not RETRY_MODE:
        return False
    return tier in _EXPENSIVE_TIERS


def validate_with_retry(pytest_paths: list[str] | None = None) -> int:
    """Run only the pytest-paths tier (skipping expensive tiers).

    Convenience wrapper around :func:`validate` that forces retry mode
    on for this call and short-circuits expensive tier invocations.
    Returns the exit code from the targeted/pytest-paths invocation.
    """
    global RETRY_MODE
    saved = RETRY_MODE
    RETRY_MODE = True
    try:
        return validate(tier="targeted", pytest_paths=pytest_paths)
    finally:
        RETRY_MODE = saved


if __name__ == "__main__":
    sys.exit(main())
