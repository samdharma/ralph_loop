"""E2E test suite — runs against `samdharma/ralph-e2e-test`.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §8.5 and §14, this test:

1. Clones `samdharma/ralph-e2e-test` into a temporary directory.
2. Copies the Ralph source into the test repo.
3. Creates a `status:ready` issue with the title prefix `[e2e-phase-<X>-run-<timestamp>]`.
4. Bootstraps the 8 required Ralph status labels on the E2E repo.
5. Runs `ralph daemon --issue=<N>` in single-issue mode.
6. Polls the issue until it reaches `status:review` or `status:blocked`.
7. Asserts a terminal status was reached.

Phase-specific tests add assertions for trajectory/idempotency artifacts (Phase B)
and the dry-run preflight gate (Phase D).

The test suite is gated on `RALPH_E2E=1` (no-op in normal CI). Each phase's
verification task (A-039, B-034, C-049, D-015) extends this file with
phase-specific assertions.

Skipped by default. To run locally:

    RALPH_E2E=1 pytest tests/e2e/test_ralph_e2e_repo.py -v

To run in CI, see `.github/workflows/e2e.yml` or `make test-e2e`.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import pytest

E2E_REPO = "samdharma/ralph-e2e-test"
E2E_REPO_URL = f"https://github.com/{E2E_REPO}.git"

# Canonical 8 labels required by `ralph daemon --dry-run`.
# Kept in sync with `core.pipeline.daemon._REQUIRED_STATUS_LABELS`.
_REQUIRED_STATUS_LABELS = (
    "status:ready",
    "status:design",
    "status:build",
    "status:verify",
    "status:review",
    "status:blocked",
    "status:build-retry",
    "status:verify-retry",
)

_LABEL_COLORS = {
    "status:ready": "0E8A16",
    "status:design": "1D76DB",
    "status:build": "0052CC",
    "status:verify": "5319E7",
    "status:review": "D4C5F9",
    "status:blocked": "B60205",
    "status:build-retry": "FBCA04",
    "status:verify-retry": "FEF2C0",
}

_TERMINAL_LABELS = {"status:review", "status:blocked"}

_E2E_POLL_INTERVAL = 15
_E2E_POLL_TIMEOUT = 25 * 60
_E2E_DAEMON_TIMEOUT = 30 * 60


def _gh(*args: str, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run `gh` and return the completed process."""
    return subprocess.run(
        ["gh", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _make_e2e_issue(phase: str, description: str, cwd: Path) -> int:
    """Create an E2E test issue on samdharma/ralph-e2e-test.

    Returns the new issue number. Title prefix matches spec §14.1 convention.
    """
    run_id = time.strftime("%Y%m%d-%H%M%S")
    title = f"[e2e-phase-{phase}-run-{run_id}] {description}"
    body = (
        f"E2E test issue created by `tests/e2e/test_ralph_e2e_repo.py`.\n\n"
        f"Phase: {phase}\n"
        f"Run ID: {run_id}\n\n"
        "This issue will be auto-closed on successful pipeline completion.\n"
        "If it reaches `status:blocked`, it is left open for operator review.\n"
    )
    result = _gh(
        "issue",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--label",
        "type:task",
        "--label",
        "status:ready",
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh issue create failed: {result.stderr}")
    # gh prints the new issue URL on stdout; the issue number is the last segment.
    issue_url = result.stdout.strip().splitlines()[-1]
    return int(issue_url.rsplit("/", 1)[-1])


def _clone_e2e_repo(tmp_path: Path) -> Path:
    """Clone `samdharma/ralph-e2e-test` into tmp_path. Returns the clone path."""
    target = tmp_path / "ralph-e2e-test"
    result = subprocess.run(
        ["git", "clone", E2E_REPO_URL, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr}")
    return target


def _copy_ralph_into(ralph_src: Path, target: Path) -> None:
    """Copy the current Ralph source tree into the target repo."""
    for item in ralph_src.iterdir():
        if item.name in {
            ".git",
            ".venv",
            "__pycache__",
            "logs",
            ".pytest_cache",
            ".mypy_cache",
            ".ralph",
        }:
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def _bootstrap_labels(repo: str) -> None:
    """Create the 8 required Ralph status labels on the E2E repo if missing.

    The daemon dry-run preflight requires these labels. Creating them
    idempotently lets the E2E test run against a fresh clone without
    relying on the repo already having a complete label set.
    """
    result = _gh("label", "list", "--repo", repo, "--json", "name", "--limit", "100")
    if result.returncode != 0:
        raise RuntimeError(f"gh label list failed: {result.stderr}")
    existing = {label["name"] for label in json.loads(result.stdout or "[]")}

    for name in _REQUIRED_STATUS_LABELS:
        if name in existing:
            continue
        create_result = _gh(
            "label",
            "create",
            name,
            "--repo",
            repo,
            "--color",
            _LABEL_COLORS[name],
            "--description",
            f"Ralph {name}",
        )
        if create_result.returncode != 0:
            raise RuntimeError(f"gh label create {name} failed: {create_result.stderr}")


def _run_engine(
    ralph_src: Path,
    target: Path,
    issue_num: Optional[int] = None,
    extra_args: Optional[list[str]] = None,
) -> subprocess.CompletedProcess:
    """Invoke ``python -m core.engine`` against the target repo.

    Sets ``PYTHONPATH`` to include both the Ralph source tree and the
    ``core/`` directory so ``from core.pipeline.shell import ...`` resolves
    correctly, and sets ``RALPH_PROJECT_DIR`` to the cloned E2E repo. The
    agent binary is propagated from the caller's ``RALPH_AGENT`` environment.
    """
    env_overrides = {
        "PYTHONPATH": f"{ralph_src}:{ralph_src / 'core'}",
        "RALPH_PROJECT_DIR": str(target),
    }
    cmd = [sys.executable, "-m", "core.engine"]
    if issue_num is not None:
        cmd += ["--issue", str(issue_num)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=ralph_src,
        capture_output=True,
        text=True,
        check=False,
        timeout=_E2E_DAEMON_TIMEOUT,
        env={**os.environ, **env_overrides},
    )


def _wait_for_terminal_status(
    issue_num: int,
    repo: str,
    timeout: int = _E2E_POLL_TIMEOUT,
    interval: int = _E2E_POLL_INTERVAL,
) -> str:
    """Poll ``gh issue view`` until the issue reaches a terminal status label.

    Returns the terminal label name (``status:review`` or ``status:blocked``).
    Raises ``TimeoutError`` if the timeout expires without reaching a terminal
    status.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = _gh(
            "issue",
            "view",
            str(issue_num),
            "--repo",
            repo,
            "--json",
            "labels",
        )
        if result.returncode == 0:
            data = json.loads(result.stdout or "{}")
            labels = {label["name"] for label in data.get("labels", [])}
            terminal = labels & _TERMINAL_LABELS
            if terminal:
                return terminal.pop()
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)
    raise TimeoutError(
        f"Issue #{issue_num} did not reach a terminal status within {timeout}s"
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RALPH_E2E") != "1",
    reason="E2E tests require RALPH_E2E=1 and a real GitHub repo",
)
def test_full_pipeline_on_e2e_repo(tmp_path: Path) -> None:
    """End-to-end: create a status:ready issue on the E2E test repo, run the
    daemon against it, and assert it reaches a terminal status.
    """
    target = _clone_e2e_repo(tmp_path)
    ralph_src = Path(__file__).resolve().parents[2]
    _copy_ralph_into(ralph_src, target)

    _bootstrap_labels(E2E_REPO)

    phase = os.environ.get("RALPH_E2E_PHASE", "a")
    issue_num = _make_e2e_issue(phase, "E2E pipeline smoke test", target)

    result = _run_engine(ralph_src, target, issue_num)
    assert result.returncode == 0, (
        f"ralph daemon --issue={issue_num} exited {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    terminal = _wait_for_terminal_status(issue_num, E2E_REPO)
    assert terminal in _TERMINAL_LABELS, f"Unexpected terminal status: {terminal}"


@pytest.mark.skipif(
    os.environ.get("RALPH_E2E") != "1",
    reason="E2E tests require RALPH_E2E=1 and a real GitHub repo",
)
def test_e2e_reachable() -> None:
    """Smoke test: the E2E repo is reachable via `gh api`.

    Runs only when RALPH_E2E=1. Confirms the operator has `gh` auth and the
    test repo is accessible. Used by the CI workflow as a precondition check.
    """
    result = _gh("api", f"repos/{E2E_REPO}", "--jq", ".name")
    assert result.returncode == 0, f"gh api failed: {result.stderr}"
    assert result.stdout.strip() == "ralph-e2e-test"


# ---------------------------------------------------------------------------
# Phase B-specific E2E assertions (B-034)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RALPH_E2E") != "1",
    reason="E2E tests require RALPH_E2E=1 and a real GitHub repo",
)
def test_phase_b_trajectory_and_idempotency_artifacts(tmp_path: Path) -> None:
    """Phase B E2E: run the daemon and verify per-issue artifacts exist.

    Per spec §10.2 B2 + B4 the engine writes:

      - .ralph/issues/<N>/idempotency.jsonl — one record per gh side effect.
      - .ralph/issues/<N>/trajectory.jsonl — one TrajectoryEvent per pipeline
        event.

    Both must exist and be non-empty after a successful pipeline run.
    """
    target = _clone_e2e_repo(tmp_path)
    ralph_src = Path(__file__).resolve().parents[2]
    _copy_ralph_into(ralph_src, target)

    _bootstrap_labels(E2E_REPO)

    issue_num = _make_e2e_issue("b", "Phase B idempotency + trajectory", target)

    result = _run_engine(ralph_src, target, issue_num)
    assert result.returncode == 0, (
        f"ralph daemon --issue={issue_num} exited {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    terminal = _wait_for_terminal_status(issue_num, E2E_REPO)
    assert terminal in _TERMINAL_LABELS, f"Unexpected terminal status: {terminal}"

    issue_dir = target / ".ralph" / "issues" / str(issue_num)
    idempotency_path = issue_dir / "idempotency.jsonl"
    trajectory_path = issue_dir / "trajectory.jsonl"

    assert (
        idempotency_path.exists() and idempotency_path.stat().st_size > 0
    ), f"Expected non-empty idempotency log at {idempotency_path}"
    assert (
        trajectory_path.exists() and trajectory_path.stat().st_size > 0
    ), f"Expected non-empty trajectory log at {trajectory_path}"


# ---------------------------------------------------------------------------
# Phase D-specific E2E assertions (D-015)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RALPH_E2E") != "1",
    reason="E2E tests require RALPH_E2E=1 and a real GitHub repo",
)
def test_phase_d_dry_run_exits_zero(tmp_path: Path) -> None:
    """Phase D E2E (D-015): dry-run gate passes and daemon reaches terminal status.

    Per spec §10.4 D E2E gate: ``ralph daemon --dry-run`` must exit 0
    on the E2E repo once the 8 status labels are in place. This test
    bootstraps the labels, asserts ``--dry-run`` exits 0, then runs the
    daemon against a phase-d issue and asserts it reaches
    ``status:review`` or ``status:blocked``.

    Note: The dry-run is a fast check (no agent invoked). For the
    parallel-BUILD 30% speedup measurement (spec §10.4 D E2E gate),
    operators must measure on a real issue via the daemon — this
    test does not measure wall-clock time.
    """
    target = _clone_e2e_repo(tmp_path)
    ralph_src = Path(__file__).resolve().parents[2]
    _copy_ralph_into(ralph_src, target)

    _bootstrap_labels(E2E_REPO)

    # Run `ralph daemon --dry-run` against the cloned repo. Labels now
    # exist, so the dry-run should exit 0.
    dry_run = _run_engine(ralph_src, target, extra_args=["--dry-run"])
    assert dry_run.returncode == 0, (
        f"ralph daemon --dry-run exited {dry_run.returncode}; "
        f"stdout={dry_run.stdout!r} stderr={dry_run.stderr!r}"
    )

    issue_num = _make_e2e_issue(
        "d", "Phase D dry-run + parallel BUILD + daemon run", target
    )

    result = _run_engine(ralph_src, target, issue_num)
    assert result.returncode == 0, (
        f"ralph daemon --issue={issue_num} exited {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    terminal = _wait_for_terminal_status(issue_num, E2E_REPO)
    assert terminal in _TERMINAL_LABELS, f"Unexpected terminal status: {terminal}"
