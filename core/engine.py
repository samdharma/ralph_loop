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
    invoke_agent,
    validate_pi_flags,
)
from core.pipeline.checkpoint import (  # noqa: E402,F401
    clear_checkpoint,
    save_checkpoint,
)
from core.pipeline.daemon import dry_run, run_loop  # noqa: E402,F401
from core.pipeline.github.comments import gh_comment  # noqa: E402,F401
from core.pipeline.github.labels import transition_label  # noqa: E402,F401
from core.pipeline.issue_ops import (  # noqa: E402,F401
    _dependencies_met,
    fetch_issue_by_number,
    fetch_ready_ticket,
    fetch_retry_issue,
    sync_ready_board,
)
from core.pipeline.prompts import _assemble_subagent_prompt  # noqa: E402,F401
from core.pipeline.providers import _classify_provider_error  # noqa: E402,F401
from core.pipeline.recovery import acquire_pid_file, release_pid_file  # noqa: E402,F401
from core.pipeline.reporting import _format_stage_failure  # noqa: E402,F401
from core.pipeline.retry import log_metrics  # noqa: E402,F401
from core.pipeline.shell import PROJECT_ROOT, gh, git  # noqa: E402,F401
from core.pipeline.stages.build_subagents import _run_test_subagent  # noqa: E402,F401
from core.pipeline.stages.verify import run_verify_stage  # noqa: E402,F401
from core.pipeline.state import STATUS_LABEL, PipelineState, Stage  # noqa: E402,F401
from core.pipeline.test_tracking import (  # noqa: E402,F401
    TamperedTestsError,
    _detect_tampered_tests,
    _resolve_existing_test_paths,
    _save_test_tracking,
    _snapshot_file_hashes,
    _snapshot_tests_dir,
)

if __name__ == "__main__":
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
