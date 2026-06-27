"""Retry budget, metrics logging, and trajectory emission (C1 step 14b).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, §7.2, §10.2 B1, B4:

  - :class:`RetryBudget` — frozen dataclass for per-stage retry
    budget read from ``.ralph/config.toml [retry]`` (per spec
    §10.2 B1 + plan §3 R-6).
  - :func:`load_retry_config` — reads ``.ralph/config.toml``.
  - :func:`_max_attempts_for_action` — derives the attempt cap
    from the action type (design/build/verify/validate) and the
    loaded :class:`RetryBudget`.
  - :func:`_invoke_with_retry` — generic retry wrapper that
    consults the budget, sleeps with backoff, and surfaces
    :class:`ProviderError` for the engine's provider-error
    handler.
  - :func:`log_metrics` — appends a structured event to
    ``ralph_metrics.jsonl``.
  - :func:`_emit_trajectory` — appends a :class:`TrajectoryEvent`
    to ``.ralph/issues/<N>/trajectory.jsonl`` for every engine
    side effect (per spec §10.2 B4.3).
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Bootstrap sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# PROJECT_ROOT and the metrics-file location live here so the
# retry/trajectory machinery does not depend on engine.py at
# module-load time (engine.py still re-exports ``log_metrics``,
# ``_emit_trajectory``, etc. for backward compatibility).
PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
LOG_DIR = PROJECT_ROOT / "logs"
METRICS_FILE = LOG_DIR / "ralph_metrics.jsonl"


# ─────────────────────────────────────────────────────────
# Retry budget (per spec §10.2 B1, plan §3 R-6)
# ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RetryBudget:
    """Per-stage retry budget read from ``.ralph/config.toml [retry]``.

    Per spec §10.2 B1 the engine consults this budget at each retry
    decision. ``l1_max_attempts`` covers transient failures
    (timeout/interrupted); ``l2_max_attempts`` covers test failures.
    """

    l1_max_attempts: int
    l2_max_attempts: int


# Per spec §10.2 B1 — defaults from plan §3 R-6 mitigation.
_DEFAULT_RETRY_BUDGET = RetryBudget(l1_max_attempts=1, l2_max_attempts=2)


def load_retry_config() -> RetryBudget:
    """Load the retry budget from ``.ralph/config.toml [retry]``.

    Per spec §10.2 B1 + plan §3 R-6:
      - missing [retry] section → defaults (l1=1, l2=2)
      - explicit values override defaults
      - invalid (negative) values → defaults + WARNING

    The config file is the engine's ``PROJECT_ROOT/.ralph/config.toml``;
    it is read once per daemon startup. Pure function: tests can
    monkeypatch ``retry.PROJECT_ROOT`` and re-call freely.
    """
    config_path = PROJECT_ROOT / ".ralph" / "config.toml"
    if not config_path.exists():
        return _DEFAULT_RETRY_BUDGET
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"[ralph] WARNING: could not read {config_path}: {e}")
        return _DEFAULT_RETRY_BUDGET
    retry_section = data.get("retry", {})

    l1 = retry_section.get("l1_max_attempts", _DEFAULT_RETRY_BUDGET.l1_max_attempts)
    l2 = retry_section.get("l2_max_attempts", _DEFAULT_RETRY_BUDGET.l2_max_attempts)

    # Per plan §3 R-6: invalid (negative) → defaults + WARNING.
    if not isinstance(l1, int) or l1 < 0:
        print(f"[ralph] WARNING: invalid l1_max_attempts={l1!r}, using default")
        l1 = _DEFAULT_RETRY_BUDGET.l1_max_attempts
    if not isinstance(l2, int) or l2 < 0:
        print(f"[ralph] WARNING: invalid l2_max_attempts={l2!r}, using default")
        l2 = _DEFAULT_RETRY_BUDGET.l2_max_attempts

    return RetryBudget(l1_max_attempts=l1, l2_max_attempts=l2)


def _max_attempts_for_action(action: str, budget: RetryBudget) -> int:
    """Return the max attempts allowed for ``action`` under ``budget``.

    ``action`` is the classifier's verdict on a previous agent
    invocation. Per spec §10.2 B1:
      - ``retry_transient`` → ``l1_max_attempts`` (default 1)
        — covers timeouts / interrupted runs.
      - ``retry_l2``       → ``l2_max_attempts`` (default 2)
        — covers test failures.
      - ``accept`` / ``block`` → 1
        — single invocation, no retry.

    Note: do NOT confuse this with the *stage* names ``build``,
    ``verify``, ``design`` etc. — those are stage identifiers in
    the pipeline, not classifier verdicts.
    """
    if action == "retry_transient":
        return budget.l1_max_attempts
    if action == "retry_l2":
        return budget.l2_max_attempts
    return 1


def _invoke_with_retry(
    prompt: str,
    issue_num: int,
    classify_fn,
    budget: RetryBudget,
) -> tuple[bool, str]:
    """Invoke the agent with retry-policy enforcement.

    Loops until either the ``classify_fn`` returns ``"accept"`` or
    ``"block"``, or the per-action retry budget is exhausted. Each
    retry inlines the previous invocation's ``stdout`` under a
    ``## Previous failure output`` header so the agent can react to
    it.

    Args:
        prompt: initial prompt to send to the agent.
        issue_num: GitHub issue number (forwarded to the agent).
        classify_fn: ``callable(str, int) -> str`` mapping
            ``(stdout, returncode)`` to an action
            (``accept | retry_l2 | retry_transient | block``).
        budget: ``RetryBudget`` from :func:`load_retry_config`.

    Returns:
        ``(success, last_stdout)`` — success is True iff the final
        action is ``accept``.
    """
    # Lazy import — invoke_agent_with_output lives in core.pipeline.agents.pi
    # (C1 step 8). ProviderError is in core.pipeline.providers (C1 step 14a).
    from core.pipeline.agents.pi import invoke_agent_with_output

    current_prompt = prompt
    last_stdout = ""
    upper_bound = max(budget.l1_max_attempts, budget.l2_max_attempts, 1)
    for attempt in range(1, upper_bound + 1):
        try:
            ok, last_stdout = invoke_agent_with_output(current_prompt, issue_num)
        except Exception:
            # ProviderError propagates without retry (engine's provider
            # handler decides whether to fall back / pause / stop).
            raise
        action = classify_fn(last_stdout, 0 if ok else 1)
        if action == "accept":
            return True, last_stdout
        if action == "block":
            return False, last_stdout
        max_for_action = _max_attempts_for_action(action, budget)
        if attempt >= max_for_action:
            print(
                f"[ralph] Retry budget exhausted for #{issue_num} "
                f"(action={action}, attempt={attempt}/{max_for_action})"
            )
            return False, last_stdout
        # Build a retry prompt that inlines the previous output.
        current_prompt = (
            f"{prompt}\n\n"
            f"## Previous failure output (attempt {attempt}, "
            f"action={action})\n\n"
            f"```\n{last_stdout}\n```\n"
        )
    return False, last_stdout


# ─────────────────────────────────────────────────────────
# Metrics logging
# ─────────────────────────────────────────────────────────


def log_metrics(event: str, **kwargs) -> None:
    """Append a structured metrics event to ``ralph_metrics.jsonl``."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ─────────────────────────────────────────────────────────
# Trajectory emission (per spec §10.2 B4.3)
# ─────────────────────────────────────────────────────────


def _emit_trajectory(
    issue_num: int,
    run_id: Optional[str],
    event_type: str,
    **payload: object,
) -> None:
    """Append a ``TrajectoryEvent`` to ``.ralph/issues/<N>/trajectory.jsonl``.

    Per spec §10.2 B4.3 every engine side effect (transition_label,
    comment, validate, etc.) emits an event. The helper is wrapped
    in a try/except so trajectory emission failures do not break
    the pipeline — the operator's experience is more important
    than the log.
    """
    try:
        from core.pipeline import metrics as _metrics
        from core.schemas.events import TrajectoryEvent

        base: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc),
            "issue_num": issue_num,
            "run_id": run_id or "",
            "event_type": event_type,
            **payload,
        }
        evt = TrajectoryEvent.model_validate(base)
        _metrics.append_trajectory_event(issue_num, evt)
    except Exception as e:  # noqa: BLE001
        print(f"[ralph] WARNING: trajectory emission failed: {e}")


__all__ = [
    "RetryBudget",
    "_DEFAULT_RETRY_BUDGET",
    "load_retry_config",
    "_max_attempts_for_action",
    "_invoke_with_retry",
    "log_metrics",
    "_emit_trajectory",
    "PROJECT_ROOT",
    "LOG_DIR",
    "METRICS_FILE",
]  # noqa: D401
