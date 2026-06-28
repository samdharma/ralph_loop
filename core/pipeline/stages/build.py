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

from core.pipeline.agents.base import create_worktree  # noqa: E402
from core.pipeline.git_ops import _rollback_working_tree  # noqa: E402
from core.pipeline.github.comments import gh_comment  # noqa: E402
from core.pipeline.reporting import (  # noqa: E402
    _extract_failure_summary,
    _format_stage_failure,
    _write_stage_report,
)
from core.pipeline.retry import log_metrics  # noqa: E402
from core.pipeline.shell import PREFLIGHT_SCRIPT, PROJECT_ROOT, run  # noqa: E402
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

    # D1.1 — parallel BUILD (opt-in via RALPH_PARALLEL_BUILD=true).
    # When enabled, run TEST + IMPLEMENT concurrently in two worktrees
    # then merge per the path-domain policy (D1.2). On overlap or
    # post-merge validate failure, fall back to sequential (D1.3).
    if _is_parallel_build_enabled():
        print(f"[ralph] Parallel BUILD enabled for #{issue_num}")
        log_metrics("build_parallel_started", issue=str(issue_num))
        try:
            test_wt, impl_wt = _parallel_create_worktrees(issue_num)
            test_ok, impl_ok = _parallel_run_subagents(test_wt, impl_wt, issue)
            if not (test_ok and impl_ok):
                # One sub-agent failed; the parallel policy's merge
                # step would not help. Fall back to sequential.
                log_metrics(
                    "build_fallback_to_sequential",
                    issue=str(issue_num),
                    reason="subagent_failed",
                )
            else:
                # Both succeeded — apply the conflict-resolution
                # policy (overlap → fallback, success → continue).
                ok = _conflict_policy(
                    issue=issue,
                    issue_num=issue_num,
                    test_wt=test_wt,
                    impl_wt=impl_wt,
                    base="HEAD",
                )
                if not ok:
                    return False
        except Exception as exc:  # noqa: BLE001
            log_metrics(
                "build_fallback_to_sequential",
                issue=str(issue_num),
                reason="parallel_setup_failed",
                detail=str(exc),
            )
            print(
                f"[ralph] Parallel BUILD setup failed for #{issue_num}: {exc}. "
                "Falling back to sequential."
            )
            # Fall through to sequential path below.
        else:
            # If we got here without exception and ok=True, run the
            # post-merge validation gate and return.
            from core.pipeline.stages.build import (  # noqa: F401
                _post_parallel_validate,
            )

            return _post_parallel_validate(issue, issue_num, is_retry)

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


# ─────────────────────────────────────────────────────────
# D1.1 — Parallel TEST + IMPLEMENT scheduler (spec §10.4 D1)
# ─────────────────────────────────────────────────────────
#
# Per spec §10.4 D1 + plan §3 R-8: ship behind
# ``RALPH_PARALLEL_BUILD=true`` config flag (default false). When
# enabled, TEST + IMPLEMENT run in two separate git worktrees
# concurrently. The path-domain merge policy (see
# :func:`_merge_worktrees`) reconciles them: ``tests/`` → TEST wins,
# ``src/`` → IMPLEMENT wins, anywhere else → FAIL FAST.


def _post_parallel_validate(issue: dict, issue_num: int, is_retry: bool) -> bool:
    """Run the validation gate after parallel BUILD's merge step.

    Per plan §3 R-8: after a successful merge, the post-merge
    validation gate re-runs ``ralph validate --tier=targeted``. On
    failure, falls back to sequential and emits a metric. The
    function is intentionally minimal — it shares logic with the
    sequential path (which lives further down in this module) but
    is invoked only when parallel mode is enabled.

    Returns ``True`` iff validation passed.
    """
    print("\n[ralph] Running validation gate (post-merge)...")
    core_dir = os.environ.get("RALPH_CORE_DIR", str(Path(__file__).parents[2]))
    qa_tests = _load_test_tracking(issue_num)
    qa_tests = [t for t in qa_tests if t.endswith(".py") and "__pycache__" not in t]
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
        val_result = run(
            validate_cmd + ["--pytest-paths"] + qa_tests,
            check=False,
            capture=True,
        )
    else:
        val_result = run(validate_cmd, check=False, capture=True)
    success = val_result.returncode == 0
    if not success:
        log_metrics(
            "build_fallback_to_sequential",
            issue=str(issue_num),
            reason="post_merge_validate_failed",
        )
        print(
            f"[ralph] Post-merge validation failed for #{issue_num}. "
            "Falling back to sequential."
        )
    return success


#
# Per spec §10.4 D1 + plan §3 R-8: ship behind
# ``RALPH_PARALLEL_BUILD=true`` config flag (default false). When
# enabled, TEST + IMPLEMENT run in two separate git worktrees
# concurrently. The path-domain merge policy (see
# :func:`_merge_worktrees`) reconciles them: ``tests/`` → TEST wins,
# ``src/`` → IMPLEMENT wins, anywhere else → FAIL FAST.


def _is_parallel_build_enabled() -> bool:
    """Return True if parallel BUILD mode is enabled.

    Resolution order:

      1. ``RALPH_PARALLEL_BUILD`` env var (``true`` / ``1`` enables;
         ``false`` / ``0`` / unset defers to config).
      2. ``[performance] parallel_build`` in ``.ralph/config.toml``.

    Per plan §3 R-8 mitigation: defaults to ``False`` so operators
    opt in. After the E2E gate confirms ≥30% speedup (spec §10.4
    E2E gate), the default can be flipped without code changes.
    """
    env_value = os.environ.get("RALPH_PARALLEL_BUILD", "").strip().lower()
    if env_value in ("1", "true", "yes", "on"):
        return True
    if env_value in ("0", "false", "no", "off"):
        return False
    # Fall through to config file.
    config_path = PROJECT_ROOT / ".ralph" / "config.toml"
    if not config_path.exists():
        return False
    try:
        import tomllib

        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    perf_section = data.get("performance", {})
    return bool(perf_section.get("parallel_build", False))


def _parallel_create_worktrees(issue_num: int) -> tuple[Path, Path]:
    """Create two worktrees for parallel TEST + IMPLEMENT.

    Returns ``(test_worktree, implement_worktree)``. The worktree
    paths are ``PROJECT_ROOT/.ralph/worktrees/<issue>-test`` and
    ``<issue>-impl`` respectively — distinct paths so the two
    sub-agents cannot interfere with each other's working copy.

    Uses the module-level ``create_worktree`` import so tests can
    patch ``build_mod.create_worktree`` to swap the implementation.
    """
    test_wt = create_worktree(f"{issue_num}-test")
    impl_wt = create_worktree(f"{issue_num}-impl")
    return test_wt, impl_wt


def _parallel_run_subagents(
    test_wt: Path, impl_wt: Path, issue: dict
) -> tuple[bool, bool]:
    """Run TEST + IMPLEMENT concurrently in two worktrees.

    Returns ``(test_ok, impl_ok)``. The implementation uses
    ``concurrent.futures.ThreadPoolExecutor`` to run the two
    sub-agents in parallel. Per plan §3 R-8 the scheduler waits
    for BOTH to complete (not the first) so the caller can merge
    the results.

    Sub-agents are launched in threads, not processes, because the
    underlying subagent invocations themselves shell out to
    ``pi``/``kimi``. Threads are sufficient; they only coordinate
    I/O-bound subprocess completion.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _run_test() -> bool:
        # Patch the issue dict's worktree context. The
        # _run_test_subagent function reads from ``build_subagents``
        # module state; we set PROJECT_ROOT temporarily to the
        # test worktree so create_worktree / worktree ops target it.
        # For now, the test/invoke paths use create_worktree
        # internally — we accept the additional worktree creation
        # inside each sub-agent (a future optimization could share
        # the worktree with the parallel scheduler).
        return _run_test_subagent(issue)

    def _run_impl() -> bool:
        return _run_implement_subagent(issue)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_test = pool.submit(_run_test)
        f_impl = pool.submit(_run_impl)
        test_ok = f_test.result()
        impl_ok = f_impl.result()
    return test_ok, impl_ok


# ─────────────────────────────────────────────────────────
# D1.3 — Conflict-resolution policy (spec §10.4 D1)
# ─────────────────────────────────────────────────────────
#
# Per plan §3 R-8: when ``merge_worktrees`` raises ``OverlapError``
# OR the post-merge validation gate fails, the build stage must
# (a) emit a metric so operators can observe how often the fallback
# triggers, and (b) fall back to sequential execution so the issue
# still progresses rather than blocking on a path-domain conflict.


def _conflict_policy(
    issue: dict,
    issue_num: int,
    test_wt: Path,
    impl_wt: Path,
    base: str,
) -> bool:
    """Apply the post-merge fallback policy.

    Tries ``merge_worktrees`` first. On ``OverlapError`` (off-domain
    overlap per plan §3 R-8 path-domain policy) OR any other merge
    failure, falls back to sequential execution:

      1. Emit a ``build_fallback_to_sequential`` metric.
      2. Re-run ``_run_test_subagent`` + ``_run_implement_subagent``
         in the parent worktree (sequential — no parallelism).
      3. Return True iff sequential succeeded.

    The metric is what operators monitor to decide whether to keep
    parallel mode enabled or roll it back. If the metric fires
    frequently, the design spec's file-ownership constraints are
    too loose and parallel BUILD isn't a net win.
    """
    from core.pipeline.agents.base import OverlapError, merge_worktrees

    try:
        merge_worktrees(test_wt, impl_wt, base=base)
        # Successful merge — no fallback needed.
        return True
    except OverlapError as exc:
        # Per plan §3 R-8: fall back to sequential execution.
        log_metrics(
            "build_fallback_to_sequential",
            issue=str(issue_num),
            reason="overlap_error",
            detail=str(exc),
        )
        print(
            f"[ralph] BUILD overlap detected for #{issue_num}: {exc}. "
            "Falling back to sequential execution."
        )
        # Sequential fallback: run TEST then IMPLEMENT in the
        # current (parent) worktree.
        if not _run_test_subagent(issue):
            return False
        if not _run_implement_subagent(issue):
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        # Any other merge failure: also fall back. Plan §3 R-8
        # says "FAIL FAST and fall back to sequential" for any
        # unresolvable conflict.
        log_metrics(
            "build_fallback_to_sequential",
            issue=str(issue_num),
            reason="merge_failed",
            detail=str(exc),
        )
        print(
            f"[ralph] BUILD merge failed for #{issue_num}: {exc}. "
            "Falling back to sequential execution."
        )
        if not _run_test_subagent(issue):
            return False
        if not _run_implement_subagent(issue):
            return False
        return True


# Re-exports for tests and consumers.
__all__ = [
    "BuildStage",
    "run_build_stage",
    "_is_parallel_build_enabled",
    "_parallel_create_worktrees",
    "_parallel_run_subagents",
    "_conflict_policy",
]
