"""Engine snapshot regression test (per plan §3 R-2).

Per docs/IMPROVEMENT_ROADMAP_PLAN.md §3 R-2 mitigation: BEFORE any
C1.x file move, snapshots of the v3.1.1 engine's behavior were
captured at ``tests/integration/fixtures/engine_snapshots/``. This
test re-runs every snapshot scenario against the (possibly moved)
engine and asserts the captured exit code and stdout pattern are
unchanged. A diff means a C1.x move introduced a behavior change;
back out the move and re-attempt.

This file is the regression guard that runs after EVERY C1.x move.
It remains in the test suite forever (not removed with the generator
script) — once C1 ships, this test serves as the safety net for
future refactors of ``core/pipeline/``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "tests" / "integration" / "fixtures" / "engine_snapshots"


def _list_snapshot_files() -> list[Path]:
    if not SNAPSHOT_DIR.exists():
        return []
    return sorted(SNAPSHOT_DIR.glob("*.json"))


SNAPSHOT_FILES = _list_snapshot_files()


@pytest.mark.skipif(
    len(SNAPSHOT_FILES) == 0,
    reason="No engine snapshots found at tests/integration/fixtures/engine_snapshots/. "
    "The one-shot generator scripts/generate_engine_snapshots.py was "
    "removed at the end of Phase C (per plan §3 R-2). Snapshots in "
    "tests/integration/fixtures/engine_snapshots/ are now the "
    "permanent regression baseline.",
)
@pytest.mark.parametrize("snapshot_path", SNAPSHOT_FILES, ids=lambda p: p.name)
def test_engine_snapshot_matches(snapshot_path: Path) -> None:
    """Re-run the scenario captured by ``snapshot_path`` and assert no diff.

    The captured ``argv`` is invoked; ``exit_code`` and ``stdout_pattern``
    (first 200 chars) must match the snapshot. ``stderr_pattern`` is
    informational — it's captured but not asserted, since stderr content
    is more prone to incidental changes (deprecation warnings, etc.).
    """
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    argv = snap["argv"]

    # Skip runtime-heavy scenarios (validate tiers, daemon, doctor with
    # no args, etc.) — they're slow and not fast-feedback-friendly.
    # They're captured for documentation but skipped at test time.
    if snap.get("skip_runtime"):
        pytest.skip(f"{snapshot_path.name}: skip_runtime=True (runtime scenario)")

    full_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=full_env,
        timeout=30,
    )

    # Exit code must match.
    assert result.returncode == snap["exit_code"], (
        f"Snapshot {snapshot_path.name} exit-code changed: "
        f"expected {snap['exit_code']}, got {result.returncode}. "
        f"This means a C1.x move introduced behavior change. "
        f"Back out the move and re-attempt."
    )

    # stdout_pattern (first 200 chars) must match.
    actual_stdout = (result.stdout or "")[:200]
    assert actual_stdout == snap["stdout_pattern"], (
        f"Snapshot {snapshot_path.name} stdout changed: "
        f"expected {snap['stdout_pattern']!r}, got {actual_stdout!r}. "
        f"This means a C1.x move introduced behavior change. "
        f"Back out the move and re-attempt."
    )
