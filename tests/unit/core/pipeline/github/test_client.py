"""Tests for core.pipeline.github.client (C1.6a).

Adds TestGitHubClientAtNewPath that verifies GitHubClient is at the
new path (from B-009) and exposes the expected API.
"""

from __future__ import annotations


class TestGitHubClientAtNewPath:
    """C1.6a: GitHubClient is at the new path."""

    def test_github_client_importable(self) -> None:
        from core.pipeline.github.client import GitHubClient

        assert GitHubClient is not None

    def test_github_client_constructor_signature(self) -> None:
        """GitHubClient(run_id=...) constructor accepts run_id kwarg."""
        import inspect

        from core.pipeline.github.client import GitHubClient

        sig = inspect.signature(GitHubClient.__init__)
        params = sig.parameters
        assert "run_id" in params
