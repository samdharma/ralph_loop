"""E2E test skeleton — runs against `samdharma/ralph-e2e-test`.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §8.5 and §14, this test:

1. Clones `samdharma/ralph-e2e-test` into a temporary directory.
2. Copies the Ralph source into the test repo.
3. Runs `ralph setup`.
4. Creates a `status:ready` issue with the title prefix `[e2e-phase-<X>-run-<timestamp>]`.
5. Runs `ralph daemon --issue=<N>` in single-issue mode.
6. Asserts the issue transitioned through DESIGN → BUILD → VERIFY.
7. Asserts a commit was made to the test repo.

The test is gated on `RALPH_E2E=1` (no-op in normal CI). Each phase's verification
task (A-039, B-034, C-049, D-015) extends this file with phase-specific assertions.

Skipped by default. To run locally:

    RALPH_E2E=1 pytest tests/e2e/test_ralph_e2e_repo.py -v

To run in CI, see `.github/workflows/e2e.yml`.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import pytest

E2E_REPO = "samdharma/ralph-e2e-test"
E2E_REPO_URL = f"https://github.com/{E2E_REPO}.git"


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
        if item.name in {".git", ".venv", "__pycache__", "logs", ".pytest_cache", ".mypy_cache"}:
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RALPH_E2E") != "1",
    reason="E2E tests require RALPH_E2E=1 and a real GitHub repo",
)
def test_full_pipeline_on_e2e_repo(tmp_path: Path) -> None:
    """End-to-end: create a status:ready issue on the E2E test repo and observe
    the pipeline progress through DESIGN → BUILD → VERIFY.

    Skeleton implementation (A-006). Phase-specific assertions are added in
    A-039 (Phase A), B-034 (Phase B), C-049 (Phase C), D-015 (Phase D).
    """
    # 1. Clone the test repo
    target = _clone_e2e_repo(tmp_path)

    # 2. Copy Ralph source into the repo
    ralph_src = Path(__file__).resolve().parents[2]
    _copy_ralph_into(ralph_src, target)

    # 3. Create a status:ready issue
    phase = os.environ.get("RALPH_E2E_PHASE", "a")
    issue_num = _make_e2e_issue(phase, "E2E pipeline smoke test", target)

    # 4. (Skeleton) The actual `ralph daemon --issue=<N>` invocation lands in
    # the phase-specific verification task. For now, just assert the issue was
    # created and the repo is reachable.
    assert issue_num > 0
    assert target.exists()

    # 5. Cleanup: leave the issue open for the operator to review the result
    # of the actual daemon run (spec §14.2 retention policy: 30 days).


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