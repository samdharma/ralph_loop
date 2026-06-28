#!/usr/bin/env python3
"""Ralph v3 — CLI entrypoint for the daemon."""

import argparse
import os
import sys
from pathlib import Path

# Ensure the project root (parent of ``core/``) is on sys.path so
# ``from core.pipeline...`` works whether engine.py is invoked as
# ``python core/engine.py`` (bin/ralph flow) or as ``python -m core.engine``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Backward-compatible re-exports for tests and callers that import from
# ``core.engine`` directly. New code should import from the canonical
# ``core.pipeline.*`` modules.
from core.pipeline.agents.pi import (  # noqa: E402,F401
    _PI_FLAGS,
    _get_kimi_session_id,
    _parse_pi_valid_flags,
    _resolve_agent_binary,
    invoke_agent,
    invoke_agent_with_output,
    validate_pi_flags,
)
from core.pipeline.artifacts_ops import (  # noqa: E402,F401
    _archive_issue_artifacts,
    _archived_issue_dir,
    _cleanup_issue_artifacts,
    _design_spec_path,
)
from core.pipeline.checkpoint import CHECKPOINT_FILE  # noqa: E402,F401
from core.pipeline.checkpoint import (  # noqa: E402,F401
    clear_checkpoint,
    save_checkpoint,
)
from core.pipeline.daemon import dry_run, run_loop  # noqa: E402,F401
from core.pipeline.git_ops import (  # noqa: E402,F401
    _has_commits,
    _has_unpushed_commits,
    _push_with_retry,
    _rollback_working_tree,
    commit_stage,
)
from core.pipeline.github.board import sync_closed, sync_status  # noqa: E402,F401
from core.pipeline.github.client import _build_github_client  # noqa: E402,F401
from core.pipeline.github.comments import gh_comment  # noqa: E402,F401
from core.pipeline.github.labels import transition_label  # noqa: E402,F401
from core.pipeline.issue_ops import (  # noqa: E402,F401
    RETRY_LABEL_MAP,
    _dependencies_met,
    _parse_depends_on,
    fetch_issue_by_number,
    fetch_ready_ticket,
    fetch_retry_issue,
    sync_ready_board,
)
from core.pipeline.prompts import (  # noqa: E402,F401
    _assemble_subagent_prompt,
    _fetch_issue_comments,
    _parse_reference_docs,
    assemble_stage_prompt,
)
from core.pipeline.providers import (  # noqa: E402,F401
    PROVIDER_QUOTA_PATTERNS,
    PROVIDER_RATE_LIMIT_PATTERNS,
    RATE_LIMIT_BACKOFF_SECONDS,
    ProviderError,
    ProviderQuotaError,
    ProviderRateLimitError,
    _classify_provider_error,
    _create_provider_issue,
    _find_alternate_agent,
    _handle_provider_error,
    _revert_to_ready,
    _sleep_with_interrupt,
)
from core.pipeline.recovery import (  # noqa: E402,F401
    RalphInterrupted,
    _check_interrupt,
    _handle_signal,
    _in_cleanup,
    _shutdown_requested,
    acquire_pid_file,
    recover_from_crash,
    release_pid_file,
)
from core.pipeline.reporting import (  # noqa: E402,F401
    _extract_failure_summary,
    _format_stage_failure,
    _read_partial_design_spec,
    _summarize_design_spec,
    _write_stage_report,
)
from core.pipeline.retry import (  # noqa: E402,F401
    _DEFAULT_RETRY_BUDGET,
    RetryBudget,
    _emit_trajectory,
    _invoke_with_retry,
    _max_attempts_for_action,
    load_retry_config,
    log_metrics,
)
from core.pipeline.runner import run_pipeline  # noqa: E402,F401
from core.pipeline.shell import (  # noqa: E402,F401
    DESIGN_SPEC_DIR,
    LOG_DIR,
    METRICS_FILE,
    PREFLIGHT_SCRIPT,
    PROJECT_ROOT,
    PROMPT_FILE,
    PROMPTS_DIR,
    gh,
    git,
    run,
)
from core.pipeline.stages.build import run_build_stage  # noqa: E402,F401
from core.pipeline.stages.build_subagents import (  # noqa: E402,F401
    _run_implement_subagent,
    _run_test_subagent,
)
from core.pipeline.stages.design import run_design_stage  # noqa: E402,F401
from core.pipeline.stages.verify import run_verify_stage  # noqa: E402,F401
from core.pipeline.state import (  # noqa: E402,F401
    STATUS_LABEL,
    PipelineState,
    Stage,
    generate_run_id,
)
from core.pipeline.test_tracking import (  # noqa: E402,F401
    TamperedTestsError,
    _detect_new_tests,
    _detect_tampered_tests,
    _file_hash,
    _load_test_tracking,
    _resolve_existing_test_paths,
    _save_test_tracking,
    _snapshot_file_hashes,
    _snapshot_tests_dir,
    _test_tracking_file,
)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        from core.migrate import main as migrate_main

        sys.exit(migrate_main(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="Ralph v3 Daemon")
    parser.add_argument(
        "--auto-close",
        action="store_true",
        help="Close issues on success instead of marking status:review",
    )
    parser.add_argument(
        "--agent",
        choices=["pi", "kimi"],
        default=None,
        help="AI agent to use (overrides RALPH_AGENT and config)",
    )
    parser.add_argument(
        "--issue",
        type=int,
        default=None,
        metavar="N",
        help="Process only issue #N and exit",
    )
    parser.add_argument(
        "--pi-flag",
        action="append",
        default=[],
        metavar="FLAG",
        help="Extra flag for every pi invocation (repeatable). "
        "Example: --pi-flag='--model=claude-sonnet-4' --pi-flag='--thinking high'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate gh/git/labels/paths without invoking the agent (per spec §10.4 D3).",
    )
    args = parser.parse_args()
    if args.agent:
        os.environ["RALPH_AGENT"] = args.agent
    if args.pi_flag:
        resolved_agent = args.agent or os.environ.get("RALPH_AGENT", "") or "pi"
        if resolved_agent != "pi":
            print(
                f"[ralph] WARNING: --pi-flag is set but agent is '{resolved_agent}' (not 'pi'). Flags will be ignored."
            )
        else:
            _PI_FLAGS[:] = validate_pi_flags(args.pi_flag)
            print(
                f"[ralph] Validated {len(args.pi_flag)} pi flag(s): {' '.join(_PI_FLAGS)}"
            )
    if args.dry_run:
        # Per spec §10.4 D3: dry-run walks the pipeline up to (but not
        # including) agent invocation. No pi/kimi subprocess is invoked.
        sys.exit(dry_run())
    run_loop(auto_close=args.auto_close, single_issue=args.issue)
