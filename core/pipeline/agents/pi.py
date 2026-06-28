"""Pi agent wrapper (C1 step 8 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the agent-invocation
machinery (invoke_agent, invoke_agent_with_output, plus the
pi-flag validation helpers and the binary-resolution helper)
lives at ``core/pipeline/agents/pi.py``.

The ``PiAgent`` ABC subclass (defined in this same module) wraps
this machinery for callers that want an OOP-style API. Per spec
§10.1 A3 (R1): no ``--continue`` / ``--session`` flags are
used — the artifact directory carries stage-to-stage context.

The kimi-specific session-UUID workaround was removed in A3.3
(plan §3 R-1); both pi and kimi use the same invocation path
now, with only the non-interactive flag differing
(``--print`` for pi, ``--prompt`` for kimi).
"""

from __future__ import annotations

import json
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

# PROJECT_ROOT is the directory containing ``.ralph/`` and the
# checkout the agent operates on. Tests override via monkeypatch.
PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))

# Per-cmd ``pi`` flags validated at startup against ``pi --help``.
# Each string may contain multiple whitespace-separated tokens.
_PI_FLAGS: list[str] = []


# ─────────────────────────────────────────────────────────
# Subprocess seam
# ─────────────────────────────────────────────────────────


def _run_agent(
    cmd: list[str],
    check: bool = False,
    capture: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run a shell command for the agent-invocation path.

    Local seam (no engine dependency) so tests can monkeypatch
    ``core.pipeline.agents.pi._run_agent`` directly without
    pulling engine into the patch graph.
    """
    return subprocess.run(  # noqa: S603
        cmd,
        capture_output=capture,
        text=False,
        check=check,
        timeout=timeout,
        cwd=PROJECT_ROOT,
    )


# ─────────────────────────────────────────────────────────
# Pi-flag validation
# ─────────────────────────────────────────────────────────


def _parse_pi_valid_flags() -> set[str]:
    """Run ``pi --help`` and return the set of valid long flag names.

    Extracts flags like ``--model``, ``--no-skills``, ``--thinking``
    from the help output. Only long-form flags are returned (``--flag``,
    not ``-f`` aliases).
    """
    try:
        result = subprocess.run(
            ["pi", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout + result.stderr
    except Exception as e:
        print(f"[ralph] ERROR: could not run 'pi --help': {e}")
        sys.exit(1)

    flags: set[str] = set()
    for line in output.splitlines():
        stripped = line.strip()
        # Lines like "  --model <pattern>  ..." or "  --no-skills  ..."
        if stripped.startswith("--"):
            # Extract flag name: everything from -- to first space/comma/end.
            flag = stripped.split()[0]
            # Handle aliases: "--continue, -c" → just "--continue".
            flag = flag.rstrip(",")
            if flag.startswith("--"):
                flags.add(flag)
    return flags


def validate_pi_flags(raw_flags: list[str]) -> list[str]:
    """Validate each ``--pi-flag`` value against the known pi flag set.

    Returns a flat list of CLI tokens (whitespace-split from each raw
    flag). Exits immediately with a helpful error if any flag is
    unknown.
    """
    valid = _parse_pi_valid_flags()
    if not valid:
        print("[ralph] ERROR: could not determine valid pi flags from 'pi --help'.")
        sys.exit(1)

    tokens: list[str] = []
    for raw in raw_flags:
        parts = raw.strip().split()
        if not parts:
            continue
        flag_name = parts[0]
        if not flag_name.startswith("--"):
            print(f"[ralph] ERROR: --pi-flag value must start with '--', got: '{raw}'")
            print("  Example: --pi-flag='--model=claude-sonnet-4'")
            sys.exit(1)
        # Strip '=value' suffix for validation.
        flag_base = flag_name.split("=")[0]
        if flag_base not in valid:
            print(f"[ralph] ERROR: unknown pi flag: '{flag_base}'")
            print(f"  Provided via: --pi-flag='{raw}'")
            similar = [f for f in sorted(valid) if flag_base.lstrip("-") in f]
            if similar:
                print(f"  Did you mean one of: {', '.join(similar[:5])}?")
            print("  Run 'pi --help' for the full list of valid flags.")
            sys.exit(1)
        tokens.extend(parts)
    return tokens


# ─────────────────────────────────────────────────────────
# Agent binary resolution
# ─────────────────────────────────────────────────────────


def _resolve_agent_binary() -> str:
    """Determine which AI agent binary to invoke.

    Resolution order:
      1. ``RALPH_AGENT`` environment variable.
      2. ``[agent].binary`` in ``.ralph/config.toml``.
      3. First available binary on PATH: ``pi``, then ``kimi``.

    Returns an empty string if no agent can be resolved.
    """
    # 1. Environment override.
    agent_bin = os.environ.get("RALPH_AGENT", "").strip()
    if agent_bin:
        return agent_bin

    # 2. Project config.
    try:
        # Lazy import — _get_config lives in core.project_sync.
        from core.project_sync import _get_config

        config = _get_config()
        configured = config.get("agent", {}).get("binary", "").strip()
        if configured:
            return configured
    except Exception:
        pass

    # 3. Auto-detect from PATH.
    for candidate in ["pi", "kimi"]:
        if subprocess.run(["which", candidate], capture_output=True).returncode == 0:
            return candidate

    return ""


def _get_kimi_session_id(project_root: Path) -> Optional[str]:
    """Find the most recent Kimi session ID for ``project_root``.

    Kimi stores a session index at
    ``<kimi-home>/session_index.jsonl``. Each line maps a workDir
    to a sessionId. We look for the latest entry whose workDir
    matches the project root.
    """
    try:
        result = subprocess.run(
            ["which", "kimi"], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            return None

        # Derive Kimi home from the binary location, e.g.
        # ``~/.kimi-code/bin/kimi``.
        kimi_bin = Path(result.stdout.strip())
        kimi_home = kimi_bin.parent.parent
        index_file = kimi_home / "session_index.jsonl"
        if not index_file.exists():
            return None

        target = project_root.resolve()
        session_id = None
        with open(index_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_workdir = entry.get("workDir")
                    if entry_workdir and Path(entry_workdir).resolve() == target:
                        session_id = entry.get("sessionId")
                except (json.JSONDecodeError, OSError):
                    continue
        return session_id
    except Exception:
        return None


# ─────────────────────────────────────────────────────────
# Agent invocation
# ─────────────────────────────────────────────────────────


def invoke_agent(
    prompt: str,
    issue_num: int,
    session_file: Optional[Path] = None,
    continue_session: bool = False,
) -> bool:
    """Invoke the AI agent (pi or kimi) with the assembled prompt.

    Per spec §10.1 A3 (R1) and plan §3 R-1: ``--continue`` and
    ``--session`` are NO LONGER used. The ``session_file`` and
    ``continue_session`` parameters are kept as no-ops for API
    compatibility with existing callers; both pi and kimi use the
    same invocation path now. The IMPLEMENT sub-agent reads its
    inputs from the artifact directory
    (``.ralph/issues/<N>/artifacts/``) instead of inheriting
    session context.

    Args:
        prompt: The assembled prompt text.
        issue_num: GitHub issue number (for logging).
        session_file: Deprecated. Ignored. (Was the path to a
            session file for pi; a text file containing a Kimi
            session UUID for kimi.)
        continue_session: Deprecated. Ignored. (Was the Mode B flag.)

    Returns True if agent exits successfully.
    """
    # Detect agent binary.
    agent_bin = _resolve_agent_binary()
    if not agent_bin:
        print(
            "[ralph] ERROR: No AI agent found (pi or kimi). "
            "Set [agent].binary in .ralph/config.toml or set RALPH_AGENT."
        )
        return False

    print(f"[ralph] Invoking {agent_bin} for #{issue_num} (artifact-based handoff)...")
    # Lazy import — log_metrics lives in core.pipeline.retry.
    from core.pipeline.retry import log_metrics

    log_metrics(
        "agent_invoke",
        issue=str(issue_num),
        agent=agent_bin,
        # No continue_session flag — always artifact-based per spec §10.1 A3.
    )

    try:
        # Unified invocation path for pi and kimi. The only differences
        # are the non-interactive flag (--print for pi, --prompt for
        # kimi). The artifact directory carries the inputs between
        # stages; session continuation is no longer used.
        if agent_bin == "pi":
            cmd = [agent_bin, "--print", "--no-skills"]
            if _PI_FLAGS:
                cmd.extend(_PI_FLAGS)
            cmd.append(prompt)
        elif agent_bin == "kimi":
            cmd = [agent_bin, "--prompt", prompt]
        else:
            print(f"[ralph] ERROR: Unknown agent '{agent_bin}'")
            return False

        # Capture output so we can detect provider-side failures, then
        # echo it to the terminal so the operator still sees the agent
        # conversation.
        result = _run_agent(cmd, check=False, capture=True, timeout=None)
        # Lazy import — _check_interrupt lives in core.pipeline.recovery
        # (C1 step 3).
        from core.pipeline.recovery import _check_interrupt

        _check_interrupt()
        if result.stdout:
            print(result.stdout.decode("utf-8", errors="replace"), end="")
        if result.stderr:
            print(
                result.stderr.decode("utf-8", errors="replace"), end="", file=sys.stderr
            )
        _check_interrupt()

        if result.returncode == 0:
            # After a successful kimi invocation that should establish
            # context (DESIGN), capture the session UUID so Mode B can
            # resume it explicitly.
            if agent_bin == "kimi" and session_file and not continue_session:
                session_id = _get_kimi_session_id(PROJECT_ROOT)
                if session_id:
                    session_file.parent.mkdir(parents=True, exist_ok=True)
                    session_file.write_text(session_id, encoding="utf-8")
                    print(f"[ralph] Saved Kimi session {session_id} for #{issue_num}")
                else:
                    print(
                        f"[ralph] WARNING: Could not determine Kimi session ID for #{issue_num}. "
                        "Mode B continuation may fail."
                    )
            return True

        # Non-zero exit: inspect output for provider-side failures.
        output = (
            (result.stdout or b"").decode("utf-8", errors="replace")
            + "\n"
            + (result.stderr or b"").decode("utf-8", errors="replace")
        )
        # Lazy import — provider error machinery lives in core.pipeline.providers.
        from core.pipeline.providers import (
            ProviderError,
            ProviderQuotaError,
            ProviderRateLimitError,
            _classify_provider_error,
        )

        kind = _classify_provider_error(output)
        if kind == "rate_limit":
            print(f"[ralph] {agent_bin} hit rate limit for #{issue_num}")
            raise ProviderRateLimitError(
                f"{agent_bin} rate limit for #{issue_num}: {output[:500]}"
            )
        if kind == "quota":
            print(f"[ralph] {agent_bin} quota exhausted for #{issue_num}")
            raise ProviderQuotaError(
                f"{agent_bin} quota exhausted for #{issue_num}: {output[:500]}"
            )

        print(f"[ralph] {agent_bin} failed for #{issue_num}")
        return False
    except subprocess.TimeoutExpired:
        print(f"[ralph] Agent timed out for #{issue_num}")
        return False
    except ProviderError:
        raise
    except Exception as e:
        print(f"[ralph] Agent invocation error: {e}")
        return False


def invoke_agent_with_output(
    prompt: str,
    issue_num: int,
) -> tuple[bool, str]:
    """Invoke the agent and return ``(ok, captured_stdout)``.

    Like :func:`invoke_agent` but returns the captured stdout so
    retry wrappers can inline it into the next prompt. Per spec
    §10.2 B1 the retry wrapper needs the previous attempt's output
    to give the agent feedback context.

    Args:
        prompt: The assembled prompt text.
        issue_num: GitHub issue number (for logging).

    Returns:
        ``(ok, captured_stdout)``. ``ok`` is True iff the underlying
        agent exits 0. ``captured_stdout`` is the agent's combined
        stdout + stderr (best effort; on subprocess error it's "").
    """
    # Eager import — the ``except (ProviderRateLimitError, ProviderQuotaError)``
    # tuple is evaluated at function scope, so these names must be bound before
    # any code that could raise (e.g. a missing agent binary raising
    # FileNotFoundError). Otherwise the generic ``except Exception`` handler
    # raises NameError instead of returning the intended error tuple.
    from core.pipeline.providers import (
        ProviderQuotaError,
        ProviderRateLimitError,
        _classify_provider_error,
    )

    agent_bin = _resolve_agent_binary()
    if not agent_bin:
        return False, ""

    if agent_bin == "pi":
        cmd = [agent_bin, "--print", "--no-skills"]
        if _PI_FLAGS:
            cmd.extend(_PI_FLAGS)
        cmd.append(prompt)
    elif agent_bin == "kimi":
        cmd = [agent_bin, "--prompt", prompt]
    else:
        return False, ""

    try:
        result = _run_agent(cmd, check=False, capture=True, timeout=None)
        stdout = (result.stdout or b"").decode("utf-8", errors="replace")
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        # Echo captured streams to the terminal so operators can follow
        # subagent progress, matching the behavior of invoke_agent.
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
        captured = stdout + stderr
        if result.returncode != 0:
            # Surface provider-side failures so the retry wrapper's caller
            # (the engine's provider-error handler) can act on them.
            kind = _classify_provider_error(captured)
            if kind == "rate_limit":
                raise ProviderRateLimitError(
                    f"{agent_bin} rate limit for #{issue_num}: {captured[:500]}"
                )
            if kind == "quota":
                raise ProviderQuotaError(
                    f"{agent_bin} quota exhausted for #{issue_num}: {captured[:500]}"
                )
        return result.returncode == 0, captured
    except (
        ProviderRateLimitError,
        ProviderQuotaError,
    ):
        raise
    except Exception as e:
        return False, f"agent invocation error: {e}"


# ─────────────────────────────────────────────────────────
# PiAgent ABC subclass
# ─────────────────────────────────────────────────────────


from core.pipeline.agents.base import AgentBase  # noqa: E402


class PiAgent(AgentBase):
    """Wrapper for the ``pi`` agent binary.

    Per spec §10.1 A3: NO ``--continue`` / ``--session`` flags.
    The implementation in :func:`invoke_agent` handles this
    constraint.
    """

    name = "pi"

    def invoke(self, *args, **kwargs):
        """Delegate to :func:`invoke_agent` with ``binary='pi'``."""
        kwargs.setdefault("binary", "pi")
        return invoke_agent(*args, **kwargs)


__all__ = [
    "invoke_agent",
    "invoke_agent_with_output",
    "_resolve_agent_binary",
    "_get_kimi_session_id",
    "_parse_pi_valid_flags",
    "validate_pi_flags",
    "_PI_FLAGS",
    "PROJECT_ROOT",
    "PiAgent",
]  # noqa: D401
