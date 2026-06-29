"""QA-written test tracking helpers.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the helpers that snapshot the
tests/ directory, detect newly-written tests, detect tampering, and
persist/load the per-issue test manifest live here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

# Bootstrap sys.path so ``from core.pipeline...`` and the
# engine module can be resolved when this file is loaded via pytest
# from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.shell import PROJECT_ROOT  # noqa: E402


def _file_hash(path: Path) -> str:
    """Return SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot_tests_dir() -> dict[str, str]:
    """Return {relative_path: content_hash} for all .py files under tests/.

    Excludes __pycache__/, .pytest_cache/, and non-.py files so that
    transient cache artifacts don't leak into the test tracking manifest.
    """
    tests_dir = PROJECT_ROOT / "tests"
    snapshot: dict[str, str] = {}
    if tests_dir.exists():
        for p in tests_dir.rglob("*"):
            if not p.is_file():
                continue
            # Exclude cache directories and non-.py files
            if any(part in ("__pycache__", ".pytest_cache") for part in p.parts):
                continue
            if p.suffix != ".py":
                continue
            snapshot[str(p.relative_to(PROJECT_ROOT))] = _file_hash(p)
    return snapshot


def _detect_new_tests(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Return paths that are new or modified between two test snapshots.

    Only includes .py files; filters out cache artifacts defensively.
    """
    return sorted(
        path
        for path, digest in after.items()
        if path not in before or before[path] != digest
        if path.endswith(".py")
    )


def _snapshot_file_hashes(paths: list[str]) -> dict[str, str]:
    """Return {relative_path: content_hash} for an explicit list of file paths.

    Paths that don't exist on disk are silently skipped.
    """
    snapshot: dict[str, str] = {}
    for p in paths:
        full = PROJECT_ROOT / p
        if full.is_file():
            snapshot[p] = _file_hash(full)
    return snapshot


def _detect_tampered_tests(test_paths: list[str]) -> bool:
    """Sanity check: every QA-written test file must have mode 0o444.

    Per spec §10.1 A2 (A2.2): the A2.1 chmod at the end of TEST stage makes
    content tampering impossible at the filesystem level. This function is a
    sanity check that the chmod is still in place after the IMPLEMENT stage.

    Returns True if all files have mode 0o444.
    Raises TamperedTestsError if any file has mode != 0o444 (or has been
    deleted/relocated), and logs at ERROR level.

    Note: signature changed from v3 (was content-hash based). The new
    mechanism-enforced check is cheaper and stronger.
    """
    tampered: list[str] = []
    for path_str in test_paths:
        full = (
            PROJECT_ROOT / path_str
            if not Path(path_str).is_absolute()
            else Path(path_str)
        )
        if not full.exists():
            tampered.append(path_str)
            continue
        mode = full.stat().st_mode & 0o777
        if mode != 0o444:
            tampered.append(path_str)

    if tampered:
        logging.error(
            "[ralph] TAMPERING DETECTED: %d QA test file(s) are not locked (mode != 0o444): %s",
            len(tampered),
            tampered,
        )
        raise TamperedTestsError(
            f"QA test file(s) not in locked state (mode != 0o444): {tampered}"
        )

    return True


class TamperedTestsError(Exception):
    """Raised when QA-written test files are no longer in the locked state.

    Per spec §10.1 A2 — the IMPLEMENT sub-agent must not be able to modify
    test files that the TEST sub-agent wrote. A2.1 enforces this with a
    chmod 0o444 lock; A2.2 detects any escape via this exception.
    """

    pass


def _test_tracking_file(issue_num: int) -> Path:
    return PROJECT_ROOT / ".ralph" / f"issue-{issue_num}-tests.json"


def _save_test_tracking(issue_num: int, test_paths: list[str]):
    """Persist the list of test files created during the TEST stage.

    Sanitizes input to exclude cache artifacts (__pycache__/, .pytest_cache/)
    and non-.py files. The agent's output is untrusted input.
    """
    sanitized = [
        p
        for p in test_paths
        if p.endswith(".py") and "__pycache__" not in p and ".pytest_cache" not in p
    ]
    path = _test_tracking_file(issue_num)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tests": sanitized}, indent=2))


def _load_test_tracking(issue_num: int) -> list[str]:
    """Load the list of test files created during the TEST stage."""
    path = _test_tracking_file(issue_num)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("tests", [])
    except Exception:
        return []


def _resolve_existing_test_paths(test_paths: list[str]) -> list[str]:
    """Filter test_paths to only those that exist on disk under PROJECT_ROOT.

    Logs a warning for any path that is missing so the operator knows a
    tracked test file has been deleted or renamed.
    """
    existing: list[str] = []
    for p in test_paths:
        full = PROJECT_ROOT / p
        if full.is_file():
            existing.append(p)
        else:
            print(f"[ralph] WARNING: tracked test file not found: {p}")
    return existing


__all__ = [
    "_file_hash",
    "_snapshot_tests_dir",
    "_detect_new_tests",
    "_snapshot_file_hashes",
    "_detect_tampered_tests",
    "TamperedTestsError",
    "_test_tracking_file",
    "_save_test_tracking",
    "_load_test_tracking",
    "_resolve_existing_test_paths",
]
