#!/usr/bin/env python3
"""Generate engine snapshots for C1 refactor regression detection.

Per plan §3 R-2 mitigation: BEFORE any C1.x file move, run this
script to capture the v3.1.1 engine's behavior in a fixture repo.
Outputs are git-tracked at tests/integration/fixtures/engine_snapshots/
and are read by tests/integration/test_engine_snapshots.py on every
C1.x commit. A snapshot diff means the move introduced behavior
change — back out the move.

This script is RUN ONCE (before C-014). After C-046, the snapshot
files remain as a permanent regression guard but this generator is
removed.

Usage:
    python scripts/generate_engine_snapshots.py [--out DIR]

Each scenario produces one JSON file:
    {
      "argv": [...],
      "exit_code": int,
      "stdout_pattern": "...",   // first 200 chars of stdout
      "stderr_pattern": "...",   // first 200 chars of stderr
      "description": "..."
    }
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "tests" / "integration" / "fixtures" / "engine_snapshots"


def _run(argv: list[str], cwd: Path, env: dict | None = None) -> dict:
    """Run a subprocess and return a snapshot dict."""
    full_env = {**os.environ, **(env or {})}
    # Force Python to use unbuffered output for predictable captures.
    full_env["PYTHONUNBUFFERED"] = "1"
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=full_env,
        timeout=30,
    )
    return {
        "argv": list(argv),
        "exit_code": result.returncode,
        "stdout_pattern": (result.stdout or "")[:200],
        "stderr_pattern": (result.stderr or "")[:200],
    }


def _scenario(
    name: str,
    argv: list[str],
    cwd: Path,
    env: dict | None = None,
    description: str = "",
    skip_runtime: bool = False,
) -> dict:
    snap = _run(argv, cwd, env)
    snap["description"] = description or name
    if skip_runtime:
        snap["skip_runtime"] = True
    return snap


def _build_scenarios(out_dir: Path) -> list[dict]:
    """Build the full scenario list. Returns a list of snapshot dicts."""
    python = sys.executable
    engine = str(REPO_ROOT / "core" / "engine.py")
    scenarios: list[dict] = []

    # ─────────────────────────────────────────────────────────
    # Block 1: help / version (no fixture needed)
    # ─────────────────────────────────────────────────────────

    # 1-10: help and version
    scenarios.append(_scenario(
        "help_no_args",
        [python, engine, "--help"],
        REPO_ROOT,
        description="engine --help exits 0 with usage",
    ))
    scenarios.append(_scenario(
        "migrate_help",
        [python, engine, "migrate", "--help"],
        REPO_ROOT,
        description="engine migrate --help exits 0 with usage",
    ))
    scenarios.append(_scenario(
        "version_short",
        [python, "-c", "import core; print(core.__version__)"],
        REPO_ROOT,
        description="import core; print version",
    ))

    # ─────────────────────────────────────────────────────────
    # Block 2: CLI argument parsing (exit codes only, no side effects)
    # ─────────────────────────────────────────────────────────

    # The migrate subcommand is special-cased; let's try it without args.
    # We expect it to fail because .ralph/ doesn't exist in cwd, but
    # the failure mode is part of the snapshot.
    scenarios.append(_scenario(
        "migrate_no_args_in_clean_dir",
        [python, engine, "migrate", "--dry-run"],
        REPO_ROOT / ".git",
        description="migrate --dry-run in a clean dir (should not crash)",
    ))

    # ─────────────────────────────────────────────────────────
    # Block 3: validate.py scenarios (independent CLI entry)
    # ─────────────────────────────────────────────────────────

    validate = str(REPO_ROOT / "core" / "validate.py")
    for tier in ("targeted", "unit", "integration"):
        scenarios.append(_scenario(
            f"validate_{tier}_tier",
            [python, validate, "--tier", tier],
            REPO_ROOT,
            description=f"validate.py --tier {tier}",
            skip_runtime=True,
        ))

    # ─────────────────────────────────────────────────────────
    # Block 4: doctor.py scenarios (independent CLI entry, B5.1)
    # ─────────────────────────────────────────────────────────

    doctor = str(REPO_ROOT / "core" / "doctor.py")
    scenarios.append(_scenario(
        "doctor_no_args",
        [python, doctor],
        REPO_ROOT,
        description="doctor with no args (default scan)",
        skip_runtime=True,
    ))
    scenarios.append(_scenario(
        "doctor_help",
        [python, doctor, "--help"],
        REPO_ROOT,
        description="doctor --help",
    ))

    # ─────────────────────────────────────────────────────────
    # Block 5: trajectory.py scenarios (B4.4)
    # ─────────────────────────────────────────────────────────

    trajectory = str(REPO_ROOT / "core" / "trajectory.py")
    scenarios.append(_scenario(
        "trajectory_no_args",
        [python, trajectory],
        REPO_ROOT,
        description="trajectory with no args (exits 1 if no issue)",
        skip_runtime=True,
    ))

    # ─────────────────────────────────────────────────────────
    # Block 6: status.py scenarios
    # ─────────────────────────────────────────────────────────

    status = str(REPO_ROOT / "core" / "status.py")
    scenarios.append(_scenario(
        "status_help",
        [python, status, "--help"],
        REPO_ROOT,
        description="status --help",
        skip_runtime=True,  # status.py ignores --help; runs main logic
    ))

    # ─────────────────────────────────────────────────────────
    # Block 7: setup.py / init.py scenarios
    # ─────────────────────────────────────────────────────────

    setup = str(REPO_ROOT / "core" / "setup.py")
    scenarios.append(_scenario(
        "setup_help",
        [python, setup, "--help"],
        REPO_ROOT,
        description="setup --help",
        skip_runtime=True,  # setup.py ignores --help; runs main logic
    ))

    init = str(REPO_ROOT / "core" / "init.py")
    scenarios.append(_scenario(
        "init_help",
        [python, init, "--help"],
        REPO_ROOT,
        description="init --help",
    ))

    # ─────────────────────────────────────────────────────────
    # Block 8: report.py / generate_test_map.py scenarios
    # ─────────────────────────────────────────────────────────

    report = str(REPO_ROOT / "core" / "report.py")
    scenarios.append(_scenario(
        "report_help",
        [python, report, "--help"],
        REPO_ROOT,
        description="report --help",
        skip_runtime=True,  # report.py prints a timestamp that varies per run
    ))

    gtm = str(REPO_ROOT / "core" / "generate_test_map.py")
    scenarios.append(_scenario(
        "generate_test_map_help",
        [python, gtm, "--help"],
        REPO_ROOT,
        description="generate_test_map --help",
    ))

    detect = str(REPO_ROOT / "core" / "detect_affected_tests.py")
    scenarios.append(_scenario(
        "detect_affected_tests_help",
        [python, detect, "--help"],
        REPO_ROOT,
        description="detect_affected_tests --help",
    ))

    # ─────────────────────────────────────────────────────────
    # Block 9: daemon CLI flag parsing (should exit on missing deps)
    # ─────────────────────────────────────────────────────────

    # daemon with --issue=99999 (no real issue, should exit cleanly)
    scenarios.append(_scenario(
        "daemon_no_issue_env",
        [python, engine],
        REPO_ROOT,
        env={"RALPH_NO_GITHUB": "1", "HOME": "/nonexistent"},
        description="daemon with no args (exits when no gh / no repo)",
        skip_runtime=True,
    ))

    # ─────────────────────────────────────────────────────────
    # Block 10: pipeline module imports (smoke check)
    # ─────────────────────────────────────────────────────────

    for mod in [
        "core.pipeline.state",
        "core.pipeline.metrics",
        "core.pipeline.agents.base",
        "core.pipeline.agents.artifacts",
        "core.pipeline.github.client",
        "core.schemas.events",
        "core.trajectory",
        "core.doctor",
        "core.migrate",
    ]:
        scenarios.append(_scenario(
            f"import_{mod.replace('.', '_')}",
            [python, "-c", f"import {mod}; print('ok')"],
            REPO_ROOT,
            description=f"import {mod}",
        ))

    # ─────────────────────────────────────────────────────────
    # Block 11: validate.py CLI flags (no run; just help)
    # ─────────────────────────────────────────────────────────

    scenarios.append(_scenario(
        "validate_help",
        [python, validate, "--help"],
        REPO_ROOT,
        description="validate --help",
    ))
    scenarios.append(_scenario(
        "validate_unquarantine_stale",
        [python, validate, "--unquarantine-stale"],
        REPO_ROOT,
        description="validate --unquarantine-stale",
        skip_runtime=True,
    ))
    scenarios.append(_scenario(
        "validate_retry",
        [python, validate, "--retry", "--tier", "targeted"],
        REPO_ROOT,
        description="validate --retry --tier targeted",
        skip_runtime=True,
    ))

    # ─────────────────────────────────────────────────────────
    # Block 12: argument-error scenarios (negative)
    # ─────────────────────────────────────────────────────────

    scenarios.append(_scenario(
        "validate_unknown_tier",
        [python, validate, "--tier", "nonexistent"],
        REPO_ROOT,
        description="validate with unknown tier (errors out cleanly)",
    ))

    # ─────────────────────────────────────────────────────────
    # Block 13: validate CLI flag combos (positive paths)
    # ─────────────────────────────────────────────────────────

    scenarios.append(_scenario(
        "validate_targeted_tier_short",
        [python, validate, "targeted"],
        REPO_ROOT,
        description="validate with positional tier argument",
    ))
    scenarios.append(_scenario(
        "validate_with_critical_flag",
        [python, validate, "--critical", "--tier", "targeted"],
        REPO_ROOT,
        description="validate --critical --tier targeted",
        skip_runtime=True,
    ))
    scenarios.append(_scenario(
        "validate_with_junitxml_flag",
        [python, validate, "--tier", "targeted", "--junitxml=/tmp/snap-junit.xml"],
        REPO_ROOT,
        description="validate with --junitxml flag",
        skip_runtime=True,
    ))
    scenarios.append(_scenario(
        "validate_help_short",
        [python, validate, "-h"],
        REPO_ROOT,
        description="validate -h short help",
    ))
    scenarios.append(_scenario(
        "validate_pytest_paths_arg",
        [python, validate, "--tier", "targeted", "--pytest-paths", "tests/unit/test_validate.py"],
        REPO_ROOT,
        description="validate with --pytest-paths argument",
        skip_runtime=True,
    ))

    # ─────────────────────────────────────────────────────────
    # Block 14: engine CLI error cases
    # ─────────────────────────────────────────────────────────

    scenarios.append(_scenario(
        "engine_unknown_flag",
        [python, engine, "--not-a-flag"],
        REPO_ROOT,
        description="engine with unknown flag (exits 2)",
    ))
    scenarios.append(_scenario(
        "engine_agent_choice",
        [python, engine, "--agent", "pi", "--help"],
        REPO_ROOT,
        description="engine --agent pi --help",
    ))
    scenarios.append(_scenario(
        "engine_pi_flag",
        [python, engine, "--pi-flag", "--model=test", "--help"],
        REPO_ROOT,
        description="engine --pi-flag with --help",
    ))
    scenarios.append(_scenario(
        "engine_auto_close_flag",
        [python, engine, "--auto-close", "--help"],
        REPO_ROOT,
        description="engine --auto-close --help",
    ))
    scenarios.append(_scenario(
        "engine_issue_flag",
        [python, engine, "--issue", "42", "--help"],
        REPO_ROOT,
        description="engine --issue 42 --help",
    ))

    # ─────────────────────────────────────────────────────────
    # Block 15: module-level imports + introspection
    # ─────────────────────────────────────────────────────────

    # Public API surface checks — verify the same symbols are importable.
    for sym_block in [
        "from core.pipeline.state import Stage, PipelineState, STATUS_LABEL",
        "from core.pipeline.metrics import append_trajectory_event, read_trajectory",
        "from core.pipeline.agents.base import AgentBase, create_worktree, remove_worktree",
        "from core.pipeline.agents.artifacts import write_design, write_files_in_scope",
        "from core.pipeline.github.client import GitHubClient",
        "from core.schemas.events import TrajectoryEvent",
        "from core.pipeline import Stage",
        "import core.engine",
        "from core.engine import run_loop",
    ]:
        scenarios.append(_scenario(
            f"api_{abs(hash(sym_block)) % 100000:05d}",
            [python, "-c", f"{sym_block}; print('ok')"],
            REPO_ROOT,
            description=f"public API: {sym_block[:60]}",
        ))

    # ─────────────────────────────────────────────────────────
    # Block 16: error-handling scenarios
    # ─────────────────────────────────────────────────────────

    scenarios.append(_scenario(
        "engine_python_syntax_error",
        [python, engine, "this_is_not_a_real_subcommand"],
        REPO_ROOT,
        description="engine with non-existent subcommand",
    ))
    scenarios.append(_scenario(
        "validate_tier_with_no_paths",
        [python, validate, "--tier", "full"],
        REPO_ROOT,
        description="validate --tier full (no paths, should run full tier)",
        skip_runtime=True,
    ))

    # ─────────────────────────────────────────────────────────
    # Block 17: bin/ralph dispatcher (preserved per spec §3.7)
    # ─────────────────────────────────────────────────────────

    bin_ralph = str(REPO_ROOT / "bin" / "ralph")
    scenarios.append(_scenario(
        "bin_ralph_help",
        ["bash", bin_ralph, "--help"],
        REPO_ROOT,
        description="bin/ralph --help (bash dispatcher)",
    ))
    scenarios.append(_scenario(
        "bin_ralph_version",
        ["bash", bin_ralph, "version"],
        REPO_ROOT,
        description="bin/ralph version (bash dispatcher)",
    ))

    return scenarios


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory for snapshot JSON files",
    )
    args = ap.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios = _build_scenarios(out_dir)
    for i, snap in enumerate(scenarios):
        name = snap.get("description", f"scenario_{i:03d}")
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        path = out_dir / f"{i:03d}_{safe}.json"
        path.write_text(json.dumps(snap, indent=2), encoding="utf-8")

    print(f"[ralph] Wrote {len(scenarios)} snapshots to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())