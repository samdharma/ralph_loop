"""Provider error handling (C1 step 14 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, §10.1 A3.2, the
provider-side error machinery lives at
``core/pipeline/providers.py``. It includes:

  - :class:`ProviderError`, :class:`ProviderRateLimitError`,
    :class:`ProviderQuotaError` — exception hierarchy for
    provider-side failures (per spec §10.2 B1.3).
  - :func:`_classify_provider_error` — inspects agent
    stdout/stderr for known rate-limit / quota patterns and
    returns ``"rate_limit"`` or ``"quota"``.
  - :func:`_find_alternate_agent` — picks a fallback agent
    binary when the current one errors out.
  - :func:`_revert_to_ready` — moves an issue back to
    ``status:ready`` after a provider error.
  - :func:`_create_provider_issue` — creates the GitHub issue
    documenting provider exhaustion.
  - :func:`_sleep_with_interrupt` — sleeps in 1-second chunks so
    SIGINT/SIGTERM can break out quickly.
  - :func:`_handle_provider_error` — the top-level dispatcher
    called from :mod:`core.engine`'s ``run_pipeline`` /
    ``run_loop`` to decide whether to retry / fall back / pause.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Bootstrap sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# RATE_LIMIT_BACKOFF_SECONDS is the global pause length used by
# ``_sleep_with_interrupt`` when all available agents are
# rate-limited. The 15-minute value matches spec §10.2 B1.3
# (long enough for transient limits to clear, short enough that
# an operator noticing the issue can intervene).
RATE_LIMIT_BACKOFF_SECONDS = 15 * 60


class ProviderError(Exception):
    """Base class for provider-side errors that Ralph should handle specially."""

    pass


class ProviderRateLimitError(ProviderError):
    """429 / rate-limit / overload: backoff and retry later."""

    pass


class ProviderQuotaError(ProviderError):
    """Quota / billing exhausted: try alternate agent or stop."""

    pass


# Patterns matched against agent stdout/stderr. Be conservative:
# normal test failures must NOT match these.
PROVIDER_RATE_LIMIT_PATTERNS = [
    r"APIProviderRateLimitError",
    r"\b429\b",
    r"rate\s*limit",
    r"too\s+many\s+requests",
    r"overloaded",
]

PROVIDER_QUOTA_PATTERNS = [
    r"GoUsageLimitError",
    r"FreeUsageLimitError",
    r"Monthly usage limit reached",
    r"available balance",
    r"insufficient_quota",
    r"out of budget",
    r"quota\s*exceeded",
    r"billing",
]


def _classify_provider_error(output: str) -> Optional[str]:
    """Classify captured agent output as a provider-side failure.

    Returns:
        ``"quota"`` if a quota/billing limit is detected,
        ``"rate_limit"`` if a rate limit / 429 is detected,
        ``None`` otherwise.
    """
    if not output:
        return None
    text = output.lower()
    for pattern in PROVIDER_QUOTA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "quota"
    for pattern in PROVIDER_RATE_LIMIT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "rate_limit"
    return None


def _find_alternate_agent(excluded: set[str]) -> Optional[str]:
    """Return an available agent binary that is not in ``excluded``."""
    for candidate in ("pi", "kimi"):
        if candidate in excluded:
            continue
        if subprocess.run(["which", candidate], capture_output=True).returncode == 0:
            return candidate
    return None


def _revert_to_ready(issue_num: int):
    """Move an issue back to ``status:ready``, removing any in-flight stage labels.

    Uses :data:`core.pipeline.state.STATUS_LABEL` for the label
    strings so the source-of-truth is the Stage enum.
    """
    # Lazy import — STATUS_LABEL lives in core.pipeline.state.
    from core.pipeline.state import STATUS_LABEL, Stage

    for label in [
        STATUS_LABEL[Stage.DESIGN],
        STATUS_LABEL[Stage.BUILD],
        STATUS_LABEL[Stage.VERIFY],
        STATUS_LABEL[Stage.REVIEW],
        STATUS_LABEL[Stage.BLOCKED],
    ]:
        try:
            # Lazy import — gh lives in core.engine at this point in
            # the cascade (will move to client.py later if needed).
            from core.engine import gh

            gh("issue", "edit", str(issue_num), "--remove-label", label)
        except subprocess.CalledProcessError:
            pass
    try:
        from core.engine import gh, sync_status

        gh("issue", "edit", str(issue_num), "--add-label", "status:ready")
        sync_status(issue_num, "status:ready")
        print(f"[ralph] #{issue_num} reverted to status:ready (provider issue)")
    except subprocess.CalledProcessError as e:
        print(f"[ralph] WARNING: could not revert #{issue_num} to status:ready: {e}")


def _create_provider_issue(agent: str, error: ProviderError) -> Optional[str]:
    """Create a GitHub issue documenting provider exhaustion and stop processing."""
    title = f"🛑 Ralph provider exhausted: {agent}"
    body = (
        f"Ralph stopped processing because `{agent}` reported a provider error:\n\n"
        f"```\n{str(error)[:2000]}\n```\n\n"
        f"- Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        f"- Action required: Check the provider account / billing / quota, "
        f"then restart the Ralph daemon.\n"
    )
    try:
        # Lazy import — gh lives in core.engine.
        from core.engine import gh, log_metrics

        result = gh(
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--label",
            "type:exit",
        )
        url = result.stdout.strip()
        print(f"[ralph] Created provider issue: {url}")
        log_metrics("provider_exhausted", agent=agent, issue_url=url)
        return url
    except subprocess.CalledProcessError as e:
        print(f"[ralph] WARNING: could not create provider issue: {e}")
        # Lazy import — log_metrics still lives in core.engine.
        from core.engine import log_metrics

        log_metrics("provider_exhausted", agent=agent, error=str(e))
        return None


def _sleep_with_interrupt(seconds: int):
    """Sleep in 1-second chunks so SIGINT/SIGTERM can break out quickly."""
    # Lazy import — _check_interrupt and _shutdown_requested live in
    # core.pipeline.recovery (C1 step 3).
    from core.pipeline.recovery import _check_interrupt, _shutdown_requested

    for _ in range(seconds):
        _check_interrupt()
        if _shutdown_requested:
            break
        time.sleep(1)


def _handle_provider_error(
    issue: dict, error: ProviderError, tried_agents: set[str]
) -> str:
    """Handle a provider-side error for the current issue.

    Returns:
        ``"continue"`` if the loop should continue (fallback or pause),
        ``"break"`` if the daemon should stop (quota exhausted, no fallback).
    """
    # Lazy imports for everything we touch from engine.py / recovery.py
    # / checkpoint.py.
    from core.engine import (
        _resolve_agent_binary,
        clear_checkpoint,
        gh_comment,
        log_metrics,
    )

    issue_num = issue["number"]
    current_agent = _resolve_agent_binary()
    if current_agent:
        tried_agents.add(current_agent)
    clear_checkpoint()

    alternate = _find_alternate_agent(tried_agents)
    if alternate:
        gh_comment(
            issue_num,
            f"⏸️ {current_agent or 'agent'} {type(error).__name__} — "
            f"trying `{alternate}`...",
        )
        _revert_to_ready(issue_num)
        os.environ["RALPH_AGENT"] = alternate
        print(f"[ralph] Switching agent to {alternate} for #{issue_num}")
        log_metrics(
            "agent_fallback",
            issue=str(issue_num),
            from_agent=current_agent or "unknown",
            to_agent=alternate,
            reason=type(error).__name__,
        )
        time.sleep(5)
        return "continue"

    if isinstance(error, ProviderRateLimitError):
        gh_comment(
            issue_num,
            "⏸️ All available agents rate-limited — pausing pipeline for 15 minutes.",
        )
        _revert_to_ready(issue_num)
        log_metrics(
            "provider_rate_limit_pause",
            issue=str(issue_num),
            agents=sorted(tried_agents),
        )
        _sleep_with_interrupt(RATE_LIMIT_BACKOFF_SECONDS)
        tried_agents.clear()
        return "continue"

    gh_comment(
        issue_num,
        "🛑 Provider quota exhausted — stopping pipeline.",
    )
    _revert_to_ready(issue_num)
    _create_provider_issue(current_agent or "unknown", error)
    return "break"


__all__ = [
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderQuotaError",
    "_classify_provider_error",
    "_find_alternate_agent",
    "_revert_to_ready",
    "_create_provider_issue",
    "_sleep_with_interrupt",
    "_handle_provider_error",
    "RATE_LIMIT_BACKOFF_SECONDS",
]  # noqa: D401
