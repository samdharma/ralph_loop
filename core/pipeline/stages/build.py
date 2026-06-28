"""BUILD stage (C1.4b — per plan §1.1 C1.4).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the BUILD stage lives at
``core/pipeline/stages/build.py``. It runs the TEST sub-agent (Mode A —
isolated) followed by the IMPLEMENT sub-agent (Mode B — inherits DESIGN
context), then executes the validation gate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Bootstrap sys.path so ``from core.pipeline...`` modules can be resolved
# when this file is loaded via pytest from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.git_ops import _rollback_working_tree  # noqa: E402
from core.pipeline.github.comments import gh_comment  # noqa: E402
from core.pipeline.reporting import (  # noqa: E402
    _extract_failure_summary,
    _format_stage_failure,
    _write_stage_report,
)
from core.pipeline.retry import log_metrics  # noqa: E402
from core.pipeline.shell import PREFLIGHT_SCRIPT, run  # noqa: E402
from core.pipeline.stages.base import Stage  # noqa: E402
from core.pipeline.stages.build_subagents import (  # noqa: E402
    _run_implement_subagent,
    _run_test_subagent,
)
from core.pipeline.test_tracking import (  # noqa: E402
    TamperedTestsError,
    _detect_tampered_tests,
    _load_test_tracking,
    _resolve_existing_test_paths,
)


def run_build_stage(issue: dict, is_retry: bool = False) -> bool:
    """
    STAGE 2: BUILD — spawns two sub-agents:
      1. TEST sub-agent (Mode A — isolated, fresh session)
      2. IMPLEMENT sub-agent (Mode B — full context)
    Sequential: TEST runs first (writes tests), then IMPLEMENT (writes code).

    Args:
        is_retry: When True, the validation gate is invoked with
            ``--retry`` so expensive tiers are skipped (spec §10.3 C4).
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
    # Snapshot QA test files before IMPLEMENT to detect tampering.
    qa_test_paths_before = _load_test_tracking(issue_num)
    qa_test_paths_before = [
        t for t in qa_test_paths_before if t.endswith(".py") and "__pycache__" not in t
    ]
    qa_test_paths_before = _resolve_existing_test_paths(qa_test_paths_before)

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

    # A2.2 sanity check: every QA-written test file must still be mode 0o444.
    # Raises TamperedTestsError if any file is unlocked or missing.
    try:
        _detect_tampered_tests(qa_test_paths_before)
    except TamperedTestsError as e:
        # Hard block per spec §10.1 A2: tampering is no longer advisory.
        _write_stage_report(
            issue_num,
            "BUILD",
            "tampering detected",
            str(e),
        )
        gh_comment(
            issue_num,
            f"🚫 IMPLEMENT sub-agent tampered with QA-written test files: {e}. "
            "Build blocked. Manual operator review required.",
        )
        log_metrics(
            "stage_complete", issue=str(issue_num), stage="build", result="tampering"
        )
        return False

    # ── Validation gate (only tests written by the independent QA session) ──
    print("\n[ralph] Running validation gate...")
    core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parents[2]))
    qa_tests = _load_test_tracking(issue_num)
    qa_tests = [
        t for t in qa_tests if t.endswith(".py") and "__pycache__" not in t
    ]  # Defense: skip cache artifacts
    qa_tests = _resolve_existing_test_paths(qa_tests)
    validate_cmd = [
        sys.executable,
        os.path.join(core_dir, "validate.py"),
        "--tier",
        "targeted",
    ]
    if is_retry:
        validate_cmd.append("--retry")

    if qa_tests:
        print(f"[ralph] Running QA-written tests from TEST stage: {qa_tests}")
        val_result = run(
            validate_cmd + ["--pytest-paths"] + qa_tests,
            check=False,
            capture=True,
        )
    else:
        print("[ralph] No QA-written tests detected; falling back to targeted tier")
        val_result = run(
            validate_cmd,
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


class BuildStage(Stage):
    """BUILD pipeline stage — runs TEST + IMPLEMENT sub-agents."""

    name = "build"

    def run(self, issue: dict, **kwargs: Any) -> bool:
        """Run the BUILD stage."""
        return run_build_stage(issue)


__all__ = ["BuildStage", "run_build_stage"]
