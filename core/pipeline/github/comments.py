"""Comment helper (C1 step 4 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, ``gh_comment`` lives at
``core/pipeline/github/comments.py``. It posts comments to GitHub
issues via the ``gh`` CLI, with optional idempotency wrapping
(per spec §10.2 B2) and a trajectory event emission
(per spec §10.2 B4.3).

The ``gh`` and ``git`` wrappers, plus the ``_build_github_client``
helper, live in ``core.pipeline.github.client`` (C1 step 6).
The trajectory event emission ``_emit_trajectory`` lives in
``core.pipeline.retry`` (per plan cascade step 14).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Bootstrap sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _run_gh(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke ``gh`` with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["gh", *argv],
        capture_output=True,
        check=False,
    )


def gh_comment(issue_num: int, body: str, run_id: Optional[str] = None) -> bool:
    """Post a comment on the GitHub issue. Fail-soft.

    When ``run_id`` is provided (or ``RALPH_RUN_ID`` is set in the
    environment) the call is wrapped in an idempotency check: the
    (run_id, "comment", issue_num, body_hash) tuple is recorded to
    ``.ralph/issues/<N>/idempotency.jsonl`` BEFORE invoking ``gh``.
    Subsequent calls with the same tuple short-circuit.

    Per spec §10.2 B2, this is what makes the engine crash-restart
    safe — a daemon SIGKILL followed by a restart must not
    double-post comments.

    Per spec §10.2 B4.3, every successful comment also emits a
    ``TrajectoryEvent`` (specifically, a SubagentInvocation-shaped
    record is emitted via ``_emit_trajectory`` so the trajectory file
    remains the canonical log of engine side effects).
    """
    if run_id is None:
        run_id = os.environ.get("RALPH_RUN_ID")

    ok: bool
    if run_id is not None:
        # _build_github_client lives in core.pipeline.github.client
        # (C1 step 6).
        from core.pipeline.github.client import _build_github_client

        gh_client = _build_github_client(run_id)
        ok = gh_client.comment(issue_num, body)
    else:
        try:
            _run_gh(["issue", "comment", str(issue_num), "--body", body])
            ok = True
        except subprocess.CalledProcessError as e:
            print(f"[ralph] WARNING: could not comment on #{issue_num}: {e}")
            ok = False
    # Trajectory: emit a SubagentInvocation-shaped event for the gh CLI.
    # Comments don't have a dedicated TrajectoryEvent variant; reusing
    # SubagentInvocation with agent_binary='gh' is the documented
    # mapping per spec §10.2 B4.
    # Lazy import — _emit_trajectory lives in core.pipeline.retry.
    from core.pipeline.retry import _emit_trajectory

    _emit_trajectory(
        issue_num,
        run_id,
        "subagent_invocation",
        agent_binary="gh",
        prompt_size_bytes=len(body),
    )
    return ok


__all__ = ["gh_comment"]
