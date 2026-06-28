"""TEST and IMPLEMENT sub-agent helpers for the BUILD stage.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1 and the Phase C extraction plan,
the sub-agent helpers that previously lived in ``core/engine.py`` now live
here so that ``core/pipeline/stages/build.py`` can be assembled without
depending on ``core.engine``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Bootstrap sys.path so ``from core.pipeline...`` modules can be resolved
# when this file is loaded via pytest from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.agents.artifacts import write_qa_tests  # noqa: E402
from core.pipeline.agents.base import (  # noqa: E402
    WorktreeError,
    create_worktree,
    remove_worktree,
)
from core.pipeline.github.comments import gh_comment  # noqa: E402
from core.pipeline.prompts import _assemble_subagent_prompt  # noqa: E402
from core.pipeline.retry import (  # noqa: E402
    _invoke_with_retry,
    _make_classifier,
    load_retry_config,
    log_metrics,
)
from core.pipeline.shell import PROJECT_ROOT  # noqa: E402
from core.pipeline.test_tracking import (  # noqa: E402
    _detect_new_tests,
    _load_test_tracking,
    _resolve_existing_test_paths,
    _save_test_tracking,
    _snapshot_tests_dir,
)


def _run_test_subagent(issue: dict) -> bool:
    """
    TEST sub-agent — Mode A (isolated, fresh session).
    Sees design spec ONLY. Writes tests that SHOULD FAIL.
    No implementation code visibility.
    Snapshots tests/ before and after so VERIFY can run only these QA-written tests.

    Per spec §10.2 B3, the agent runs inside a git worktree so it
    cannot corrupt the parent repo. ``create_worktree`` runs first;
    ``remove_worktree`` runs in a finally block to survive failures.

    The agent is invoked through the retry-policy wrapper. Non-zero
    exits with timeout/interrupted/killed/timed-out signals are retried
    under the L1 budget; other non-zero exits are retried under the L2
    budget (default 2 attempts). On success, QA-written tests are saved,
    synced to the artifact directory, and chmod'd to 0o444.
    """
    issue_num = issue["number"]

    print(f"\n  [ralph] BUILD / TEST sub-agent for #{issue_num} (Mode A — isolated)")
    gh_comment(issue_num, "🧪 TEST sub-agent started (isolated).")
    log_metrics("subagent_start", issue=str(issue_num), subagent="test", mode="A")

    wt_path: Optional[Path] = None
    try:
        wt_path = create_worktree(issue_num)
    except WorktreeError as e:
        # Worktree isolation is a hard requirement (Phase D follow-up B3).
        # Do not fall back to the repo root; block the issue instead.
        print(f"[ralph] ERROR: worktree creation failed for #{issue_num}: {e}")
        gh_comment(
            issue_num,
            "🚫 BUILD blocked: unable to create isolated git worktree. "
            "Worktree isolation is required; check daemon logs for details.",
        )
        log_metrics(
            "worktree_failed",
            issue=str(issue_num),
            subagent="test",
            detail=str(e),
        )
        return False

    try:
        before_tests = _snapshot_tests_dir()
        prompt = _assemble_subagent_prompt(issue, "test.md", mode="A")
        success, _ = _invoke_with_retry(
            prompt,
            issue_num,
            _make_classifier("test"),
            load_retry_config(),
            stage="test",
        )
        after_tests = _snapshot_tests_dir()
        new_tests = _detect_new_tests(before_tests, after_tests)
        _save_test_tracking(issue_num, new_tests)
        # R1: keep the artifact directory in sync with the QA-written tests.
        write_qa_tests(issue_num, new_tests)
        if new_tests:
            print(f"  [ralph] TEST stage created/modified tests: {new_tests}")
            gh_comment(
                issue_num,
                f"🧪 TEST stage produced {len(new_tests)} test file(s): "
                f"{', '.join(new_tests)}",
            )

        if success:
            # A2.1: hard-block test tampering — chmod the QA-written test files
            # to 0o444 so the IMPLEMENT sub-agent cannot modify them. Idempotent.
            if new_tests:
                for rel_path in new_tests:
                    abs_path = (
                        PROJECT_ROOT / rel_path
                        if not Path(rel_path).is_absolute()
                        else Path(rel_path)
                    )
                    if abs_path.exists():
                        try:
                            os.chmod(abs_path, 0o444)
                            print(f"[ralph] Locked QA test: {rel_path} (mode 0o444)")
                        except OSError as e:
                            print(f"[ralph] WARNING: failed to chmod {rel_path}: {e}")
            gh_comment(issue_num, "✅ TEST sub-agent completed.")
        else:
            gh_comment(
                issue_num,
                "❌ TEST sub-agent failed (non-zero exit). "
                "Check daemon logs for the agent conversation output.",
            )
        log_metrics(
            "subagent_complete",
            issue=str(issue_num),
            subagent="test",
            mode="A",
            result="success" if success else "failure",
            test_count=len(new_tests) if new_tests else 0,
        )
        return success
    finally:
        if wt_path is not None:
            remove_worktree(wt_path)


def _run_implement_subagent(issue: dict) -> bool:
    """
    IMPLEMENT sub-agent — Mode B (inherits DESIGN context via artifacts).
    Reads the DESIGN artifacts and the QA-written test list, then
    implements code to make those tests pass.

    The agent is invoked through the retry-policy wrapper. Non-zero
    exits with timeout/interrupted/killed/timed-out signals are retried
    under the L1 budget; other non-zero exits are retried under the L2
    budget (default 2 attempts).
    """
    issue_num = issue["number"]
    print(
        f"\n  [ralph] BUILD / IMPLEMENT sub-agent for #{issue_num} (Mode B — inherits DESIGN context)"
    )
    gh_comment(issue_num, "🛠️ IMPLEMENT sub-agent started (continuing DESIGN context).")
    log_metrics("subagent_start", issue=str(issue_num), subagent="implement", mode="B")

    prompt = _assemble_subagent_prompt(issue, "implement.md", mode="B")

    # Inject the exact list of QA-written test files so the agent knows
    # precisely which tests it must pass — not just the TEST_MAP-based
    # set produced by `ralph validate --tier=targeted`.
    qa_tests = _load_test_tracking(issue_num)
    qa_tests = [t for t in qa_tests if t.endswith(".py") and "__pycache__" not in t]
    qa_tests = _resolve_existing_test_paths(qa_tests)
    if qa_tests:
        test_list = "\n".join(f"  - {t}" for t in qa_tests)
        prompt += (
            f"\n\n## QA-Written Test Files (must pass)\n\n"
            f"These test files were written by the independent QA sub-agent. "
            f"You MUST run these specific tests and ensure they pass:\n\n"
            f"{test_list}\n\n"
            f"Run them with:\n"
            f"  ralph validate --tier=targeted --pytest-paths {' '.join(qa_tests)}\n"
        )

    success, _ = _invoke_with_retry(
        prompt,
        issue_num,
        _make_classifier("implement"),
        load_retry_config(),
        stage="implement",
    )

    if success:
        gh_comment(issue_num, "✅ IMPLEMENT sub-agent completed.")
    else:
        gh_comment(
            issue_num,
            "❌ IMPLEMENT sub-agent failed (non-zero exit). "
            "Check daemon logs for the agent conversation output.",
        )
    log_metrics(
        "subagent_complete",
        issue=str(issue_num),
        subagent="implement",
        mode="B",
        result="success" if success else "failure",
    )
    return success


__all__ = ["_run_test_subagent", "_run_implement_subagent"]
