"""Tests for ralph setup command.

Covers the label validation in ``core/setup.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

from core import setup  # noqa: E402


class TestCheckGhLabels:
    """``check_gh_labels`` validates the required label set."""

    def _make_remote_result(
        self, remote: str = "git@github.com:samdharma/Ralph_loop.git"
    ):
        return mock.Mock(returncode=0, stdout=remote, stderr="")

    def _make_label_result(self, labels: list[str]):
        payload = [{"name": name} for name in labels]
        return mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")

    def test_all_required_labels_present_passes(self, monkeypatch: pytest.MonkeyPatch):
        """All documented labels are present → check passes."""
        required = [
            "status:ready",
            "status:design",
            "status:build",
            "status:build-retry",
            "status:verify",
            "status:verify-retry",
            "status:review",
            "status:blocked",
        ]

        def fake_run(args, **kwargs):
            if args[:2] == ["git", "remote"]:
                return self._make_remote_result()
            if args[:2] == ["gh", "label"]:
                return self._make_label_result(required)
            return mock.Mock(returncode=1, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        ok, detail = setup.check_gh_labels()
        assert ok is True
        assert "all required labels present" in detail

    def test_missing_retry_labels_fails(self, monkeypatch: pytest.MonkeyPatch):
        """Missing status:build-retry and status:verify-retry → check fails."""
        labels = [
            "status:ready",
            "status:design",
            "status:build",
            "status:verify",
            "status:review",
            "status:blocked",
        ]

        def fake_run(args, **kwargs):
            if args[:2] == ["git", "remote"]:
                return self._make_remote_result()
            if args[:2] == ["gh", "label"]:
                return self._make_label_result(labels)
            return mock.Mock(returncode=1, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        ok, detail = setup.check_gh_labels()
        assert ok is False
        assert "status:build-retry" in detail
        assert "status:verify-retry" in detail
