"""
Unit tests for core/status.py (D3.2 dry-run path).

Per spec §10.4 D3 + plan §2.4 order 1: ``ralph status --dry-run`` is
intended for CI health checks. It validates gh/git/labels WITHOUT
listing issues. Exits 0 on success.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

# The status module exposes ``main()``; we monkey-patch ``main`` to read
# the dry-run path.
import core.status as status_mod  # noqa: E402
from core.pipeline import shell as shell_mod  # noqa: E402

# ─────────────────────────────────────────────────────────
# D3.2 — ralph status --dry-run (spec §10.4 D3)
# ─────────────────────────────────────────────────────────


class TestStatusDryRun:
    """D3.2: ``ralph status --dry-run`` validates env without listing issues."""

    def _invoke_main(self, argv: list[str]) -> int:
        """Invoke status.main with the given argv; return exit code."""
        with mock.patch.object(sys, "argv", ["status"] + argv):
            return status_mod.main()

    def test_dry_run_invokes_gh_auth_status(self, tmp_path, monkeypatch) -> None:
        """``--dry-run`` invokes ``gh auth status``."""
        monkeypatch.setattr(shell_mod, "PROJECT_ROOT", tmp_path)
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(shell_mod, "gh") as gh_mock,
            mock.patch.object(shell_mod, "git") as git_mock,
        ):
            git_mock.return_value = mock.Mock(
                returncode=0,
                stdout="origin\tgit@github.com:foo/bar.git\n",
                stderr="",
            )
            gh_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            def fake_gh(*args, **kwargs):
                if args and args[0] == "label" and args[1] == "list":
                    return mock.Mock(
                        returncode=0,
                        stdout=json.dumps(
                            [
                                {"name": "status:ready"},
                                {"name": "status:design"},
                                {"name": "status:build"},
                                {"name": "status:verify"},
                                {"name": "status:review"},
                                {"name": "status:blocked"},
                                {"name": "status:build-retry"},
                                {"name": "status:verify-retry"},
                            ]
                        ),
                        stderr="",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            gh_mock.side_effect = fake_gh

            rc = self._invoke_main(["--dry-run"])

        assert rc == 0
        # gh auth status was called
        assert any(
            call_args and call_args[0] and "auth" in call_args[0]
            for call_args in gh_mock.call_args_list
        ), f"Expected `gh auth` invocation; got: {gh_mock.call_args_list}"

    def test_dry_run_validates_eight_status_labels(self, tmp_path, monkeypatch) -> None:
        """``--dry-run`` validates the 8 status labels exist."""
        monkeypatch.setattr(shell_mod, "PROJECT_ROOT", tmp_path)
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(shell_mod, "gh") as gh_mock,
            mock.patch.object(shell_mod, "git") as git_mock,
        ):
            git_mock.return_value = mock.Mock(
                returncode=0,
                stdout="origin\tgit@github.com:foo/bar.git\n",
                stderr="",
            )
            gh_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            def fake_gh(*args, **kwargs):
                if args and args[0] == "label" and args[1] == "list":
                    return mock.Mock(
                        returncode=0,
                        stdout=json.dumps([{"name": "status:ready"}]),
                        stderr="",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            gh_mock.side_effect = fake_gh

            rc = self._invoke_main(["--dry-run"])

        # Should fail (missing 7 labels).
        assert rc != 0

    def test_dry_run_does_not_invoke_gh_issue_list(self, tmp_path, monkeypatch) -> None:
        """``--dry-run`` does NOT invoke ``gh issue list`` (no listing)."""
        monkeypatch.setattr(shell_mod, "PROJECT_ROOT", tmp_path)
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        with (
            mock.patch.object(shell_mod, "gh") as gh_mock,
            mock.patch.object(shell_mod, "git") as git_mock,
        ):
            git_mock.return_value = mock.Mock(
                returncode=0,
                stdout="origin\tgit@github.com:foo/bar.git\n",
                stderr="",
            )
            gh_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            def fake_gh(*args, **kwargs):
                if args and args[0] == "label" and args[1] == "list":
                    return mock.Mock(
                        returncode=0,
                        stdout=json.dumps(
                            [
                                {"name": "status:ready"},
                                {"name": "status:design"},
                                {"name": "status:build"},
                                {"name": "status:verify"},
                                {"name": "status:review"},
                                {"name": "status:blocked"},
                                {"name": "status:build-retry"},
                                {"name": "status:verify-retry"},
                            ]
                        ),
                        stderr="",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            gh_mock.side_effect = fake_gh

            self._invoke_main(["--dry-run"])

        # No gh issue list invocation
        for call_args in gh_mock.call_args_list:
            argv = call_args[0]
            assert not (
                argv and "issue" in argv and "list" in argv
            ), f"--dry-run should not invoke gh issue list; got argv={argv}"
