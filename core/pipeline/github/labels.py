"""Label transition helper (C1 step 5 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, ``transition_label``
lives at ``core/pipeline/github/labels.py``. It updates issue
labels via ``gh issue edit`` with retry-on-transient-failure and
optional idempotency wrapping (when ``run_id`` is provided).

The underlying ``gh`` wrapper and ``_build_github_client`` factory
live in ``core.pipeline.github.client`` (C1 step 6). The
``sync_status`` board mirror and the ``_emit_trajectory`` event
emission live in ``core.pipeline.github.board`` and
``core.pipeline.retry`` respectively (per plan cascade steps 6
and 14).
"""

from __future__ import annotations

import subprocess
import sys
import time
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


def transition_label(
    issue_num: int,
    add: str,
    remove: Optional[str] = None,
    retries: int = 3,
    backoff: float = 2.0,
    run_id: Optional[str] = None,
):
    """Update issue labels via ``gh issue edit``. Retries on transient failures.

    When ``run_id`` is provided the call is wrapped in an idempotency
    check via :class:`GitHubClient`. The ``(run_id, action, issue_num,
    label-pair-hash)`` tuple is recorded to
    ``.ralph/issues/<N>/idempotency.jsonl`` BEFORE invoking ``gh``.
    Subsequent calls with the same tuple short-circuit and return
    without invoking ``gh``.

    Per spec §10.2 B2 this is what makes the engine crash-restart
    safe — a daemon SIGKILL followed by a restart must not
    double-transition labels.
    """
    if run_id is not None:
        # Lazy import — _build_github_client lives in
        # core.pipeline.github.client (C1 step 6).
        from core.pipeline.github.client import _build_github_client

        gh_client = _build_github_client(run_id)
        ok = gh_client.transition_label(
            issue_num, [add] if add else [], [remove] if remove else []
        )
        if ok:
            print(
                f"[ralph] #{issue_num} labels: +{add}"
                + (f" / -{remove}" if remove else "")
            )
            # Lazy import — sync_status lives in core.pipeline.github.board
            # (will move in step 6 if not already there).
            from core.project_sync import sync_status as _sync_status

            _sync_status(issue_num, add)
            # Lazy import — _emit_trajectory lives in core.engine at this
            # point in the cascade (will move to retry.py in step 14).
            from core.engine import _emit_trajectory

            _emit_trajectory(
                issue_num,
                run_id,
                "label_transition",
                added=[add] if add else [],
                removed=[remove] if remove else [],
            )
        return

    cmd = ["issue", "edit", str(issue_num), "--add-label", add]
    if remove:
        cmd += ["--remove-label", remove]

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            _run_gh(cmd)
            action = f"+{add}"
            if remove:
                action += f" / -{remove}"
            print(f"[ralph] #{issue_num} labels: {action}")
            # Mirror the new label to the GitHub Project board column.
            from core.project_sync import sync_status as _sync_status

            _sync_status(issue_num, add)
            # Lazy import — _emit_trajectory lives in core.engine at this
            # point in the cascade (will move to retry.py in step 14).
            from core.engine import _emit_trajectory

            _emit_trajectory(
                issue_num,
                run_id,
                "label_transition",
                added=[add] if add else [],
                removed=[remove] if remove else [],
            )
            return
        except subprocess.CalledProcessError as e:
            last_error = e
            if attempt < retries:
                wait = backoff**attempt
                print(
                    f"[ralph] Label transition failed (attempt {attempt}/{retries}), "
                    f"retrying in {wait:.0f}s..."
                )
                # Lazy import — _check_interrupt lives in core.pipeline.recovery
                # (C1 step 3).
                from core.pipeline.recovery import _check_interrupt

                _check_interrupt()
                time.sleep(wait)
    # All retries exhausted.
    if last_error is None:
        raise RuntimeError("transition_label exhausted retries with no error")
    raise last_error


__all__ = ["transition_label"]
