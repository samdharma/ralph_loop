"""``ralph trajectory <N>`` command.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §5.2 and §10.2 B4.

Reads ``.ralph/issues/<N>/trajectory.jsonl`` and prints a human-readable
timeline. Output format::

    2026-06-27T15:30:01  stage_transition   ready -> design
    2026-06-27T15:35:12  validation_run    exit=0 action=accept

Per-event details:

  - ``stage_transition``: from_stage → to_stage.
  - ``subagent_invocation``: agent=<binary> prompt=<size>B.
  - ``validation_run``: exit=<code> action=<accept|...>.
  - ``label_transition``: +<added> -<removed>.
  - ``retry``: attempt=<n> prev=<classification>.

When the trajectory file is missing, the command exits non-zero with a
clear message naming the issue number.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.schemas.events import TrajectoryEvent

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


def _trajectory_path(issue_num: int) -> Path:
    """Return the on-disk path for issue ``issue_num``'s trajectory."""
    return PROJECT_ROOT / ".ralph" / "issues" / str(issue_num) / "trajectory.jsonl"


def _format_event(evt: TrajectoryEvent) -> str:
    """Format a single event as a single line of timeline text."""
    ts: str = evt.timestamp.isoformat(timespec="seconds")  # type: ignore[attr-defined]
    inner = evt.root
    et = inner.event_type
    if et == "stage_transition":
        # Type narrow: mypy can't follow the discriminator, so we
        # use getattr with a sentinel for the attribute access.
        from_stage = getattr(inner, "from_stage", "?")
        to_stage = getattr(inner, "to_stage", "?")
        return f"{ts}  stage_transition   {from_stage} -> {to_stage}"
    if et == "subagent_invocation":
        agent_binary = getattr(inner, "agent_binary", "?")
        prompt_size_bytes = getattr(inner, "prompt_size_bytes", 0)
        return (
            f"{ts}  subagent_invocation  "
            f"agent={agent_binary} prompt={prompt_size_bytes}B"
        )
    if et == "validation_run":
        exit_code = getattr(inner, "exit_code", 0)
        action = getattr(inner, "action", "?")
        return f"{ts}  validation_run    exit={exit_code} action={action}"
    if et == "label_transition":
        added_list = getattr(inner, "added", []) or []
        removed_list = getattr(inner, "removed", []) or []
        added = "+".join(added_list)
        removed = "-" + "-".join(removed_list)
        return f"{ts}  label_transition   {added} {removed}".rstrip()
    if et == "retry":
        attempt = getattr(inner, "attempt", 0)
        prev = getattr(inner, "previous_classification", "?")
        return f"{ts}  retry             attempt={attempt} prev={prev}"
    return f"{ts}  {et}"


def print_trajectory(issue_num: int) -> None:
    """Print the timeline of trajectory events for issue ``issue_num``.

    Exits with status 1 if ``.ralph/issues/<N>/trajectory.jsonl``
    doesn't exist; the message names the issue number so the operator
    knows which trajectory to investigate.
    """
    path = _trajectory_path(issue_num)
    if not path.exists():
        print(
            f"[ralph] no trajectory recorded for issue #{issue_num} "
            f"(expected at {path})",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read JSONL directly so we don't depend on metrics module's
    # PROJECT_ROOT (tests may have patched it differently).
    events: list[TrajectoryEvent] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        import json

        events.append(TrajectoryEvent.model_validate(json.loads(raw_line)))

    print(f"Trajectory for issue #{issue_num} ({len(events)} events):")
    for evt in events:
        print(f"  {_format_event(evt)}")


__all__ = ["print_trajectory", "PROJECT_ROOT"]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m core.trajectory``.

    Usage:
        python core/trajectory.py <issue_num>
        bin/ralph trajectory <issue_num>
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Print the trajectory timeline for an issue."
    )
    parser.add_argument(
        "issue_num",
        type=int,
        help="GitHub issue number whose trajectory to print.",
    )
    args = parser.parse_args(argv)

    try:
        print_trajectory(args.issue_num)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
