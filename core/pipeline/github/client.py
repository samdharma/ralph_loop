"""Idempotent GitHub client.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §7.2 and §10.2 B2.

The :class:`GitHubClient` wraps every ``gh`` call in a pre-flight
idempotency check. The check keys on ``(run_id, action, target,
body_hash)`` and consults ``.ralph/issues/<N>/idempotency.jsonl``:

  - If the key was already executed in this ``run_id``, short-circuit
    (do not call ``gh``).
  - Otherwise, record the key, invoke ``gh``, and append the actual
    return code to the same record.

The wrapper exists in service of crash-restart resilience per plan §3
R-3: after a daemon SIGKILL the next daemon process can safely
re-attempt any pipeline step without double-posting comments or
double-transitioning labels.

Path layout:

  - Idempotency log: ``PROJECT_ROOT/.ralph/issues/<N>/idempotency.jsonl``
  - The log is JSONL; each line is one record.

The ``_run_gh`` helper is the single seam that touches ``subprocess``
— patched in tests via ``unittest.mock.patch.object``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


def _run_gh(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke the ``gh`` CLI with the given arguments.

    This is the only place that touches ``subprocess`` for GitHub
    operations. Tests patch this seam via ``unittest.mock.patch.object``.
    """
    return subprocess.run(  # noqa: S603
        ["gh", *argv],
        capture_output=True,
        check=False,
    )


def _idempotency_path(issue_num: int, project_root: Optional[Path] = None) -> Path:
    """Return the on-disk path for issue ``issue_num``'s idempotency log.

    ``project_root`` defaults to the module-level :data:`PROJECT_ROOT`
    constant but may be overridden by callers (e.g. the engine
    monkeypatches ``PROJECT_ROOT`` per-test).
    """
    root = project_root if project_root is not None else PROJECT_ROOT
    return root / ".ralph" / "issues" / str(issue_num) / "idempotency.jsonl"


def _body_hash(body: str) -> str:
    """Stable short hash of a comment body, used in idempotency keys."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


class GitHubClient:
    """Idempotent wrapper over the ``gh`` CLI.

    Every method records ``(run_id, action, target, body_hash)`` to
    the issue's idempotency log BEFORE invoking ``gh``. If a record
    with the same key already exists for this ``run_id``, the call
    short-circuits and returns ``True`` without re-invoking ``gh``.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    # ------------------------------------------------------------------
    # Public API.
    # ------------------------------------------------------------------

    def comment(self, issue_num: int, body: str) -> bool:
        """Post a comment on the issue. Idempotent within ``run_id``."""
        key = (self.run_id, "comment", str(issue_num), _body_hash(body))
        if self._already_executed(key):
            return True
        result = _run_gh(["issue", "comment", str(issue_num), "--body", body])
        self._record(key, result.returncode)
        return result.returncode == 0

    def transition_label(
        self,
        issue_num: int,
        add: list[str],
        remove: list[str],
    ) -> bool:
        """Add/remove labels on the issue. Idempotent within ``run_id``.

        The idempotency key covers the full ``(add, remove)`` pair so
        partial overlaps do NOT short-circuit (they are genuinely
        different operations).
        """
        key = (
            self.run_id,
            "transition_label",
            str(issue_num),
            _body_hash(",".join(sorted(add)) + "|" + ",".join(sorted(remove))),
        )
        if self._already_executed(key):
            return True
        argv = ["issue", "edit", str(issue_num)]
        for label in add:
            argv += ["--add-label", label]
        for label in remove:
            argv += ["--remove-label", label]
        result = _run_gh(argv)
        self._record(key, result.returncode)
        return result.returncode == 0

    # ------------------------------------------------------------------
    # Idempotency log helpers.
    # ------------------------------------------------------------------

    def _already_executed(self, key: tuple[str, str, str, str]) -> bool:
        """Return True if ``key`` was already recorded in this ``run_id``."""
        path = _idempotency_path(int(key[2]), project_root=PROJECT_ROOT)
        if not path.exists():
            return False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if (
                record.get("run_id") == key[0]
                and record.get("action") == key[1]
                and record.get("target") == key[2]
                and record.get("body_hash") == key[3]
            ):
                return True
        return False

    def _record(
        self,
        key: tuple[str, str, str, str],
        returncode: int,
    ) -> None:
        """Append one record to the issue's idempotency log."""
        path = _idempotency_path(int(key[2]), project_root=PROJECT_ROOT)
        path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": key[0],
            "action": key[1],
            "target": key[2],
            "body_hash": key[3],
            "returncode": returncode,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record))
            f.write("\n")


__all__ = ["GitHubClient", "PROJECT_ROOT"]
