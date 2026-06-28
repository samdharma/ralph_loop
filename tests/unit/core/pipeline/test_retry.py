"""Tests for core.pipeline.retry B1 retry budget wiring."""

from __future__ import annotations

from unittest import mock

import pytest

from core.pipeline.providers import (
    ProviderQuotaError,
    ProviderRateLimitError,
)
from core.pipeline.retry import (
    RetryBudget,
    _classify_subagent_result,
    _invoke_with_retry,
    _make_classifier,
)
from core.pipeline.stages import build_subagents


class TestClassifySubagentResult:
    """B1 classifier maps subagent output to the correct retry action."""

    def test_returncode_zero_is_accept(self) -> None:
        assert _classify_subagent_result("ok", 0, "design") == "accept"
        assert _classify_subagent_result("ok", 0, "test") == "accept"

    def test_design_nonzero_is_block(self) -> None:
        assert _classify_subagent_result("failed", 1, "design") == "block"

    def test_transient_signals_are_retry_transient(self) -> None:
        for signal in ("timeout", "interrupted", "killed", "timed-out"):
            assert (
                _classify_subagent_result(f"process {signal}", 1, "test")
                == "retry_transient"
            )

    def test_build_nonzero_is_retry_l2(self) -> None:
        assert _classify_subagent_result("AssertionError", 1, "test") == "retry_l2"
        assert _classify_subagent_result("AssertionError", 1, "implement") == "retry_l2"

    def test_provider_signal_is_block(self) -> None:
        assert (
            _classify_subagent_result("APIProviderRateLimitError: 429", 1, "test")
            == "block"
        )
        assert (
            _classify_subagent_result("insufficient_quota", 1, "implement") == "block"
        )
        # Provider signal wins even when returncode is 0.
        assert (
            _classify_subagent_result("Monthly usage limit reached", 0, "test")
            == "block"
        )

    def test_make_classifier_binds_stage(self) -> None:
        classifier = _make_classifier("design")
        assert classifier("failed", 1) == "block"


class TestInvokeWithRetry:
    """B1 retry wrapper consults the classifier and budget."""

    def _patch_agent(self, monkeypatch, side_effect):
        from core.pipeline.agents import pi as pi_mod

        fake = mock.Mock(side_effect=side_effect)
        monkeypatch.setattr(pi_mod, "invoke_agent_with_output", fake)
        return fake

    def test_retry_l2_reinvokes_up_to_budget(self, monkeypatch) -> None:
        budget = RetryBudget(l1_max_attempts=1, l2_max_attempts=2)
        fake = self._patch_agent(
            monkeypatch,
            side_effect=[
                (False, "first failure"),
                (True, "second success"),
            ],
        )

        ok, stdout = _invoke_with_retry("prompt", 1, _make_classifier("test"), budget)

        assert ok is True
        assert stdout == "second success"
        assert fake.call_count == 2
        # Retry prompt includes previous failure output.
        assert "first failure" in fake.call_args_list[1][0][0]

    def test_retry_transient_reinvokes_up_to_budget(self, monkeypatch) -> None:
        budget = RetryBudget(l1_max_attempts=2, l2_max_attempts=2)
        fake = self._patch_agent(
            monkeypatch,
            side_effect=[
                (False, "killed by signal"),
                (True, "recovered"),
            ],
        )

        ok, stdout = _invoke_with_retry("prompt", 1, _make_classifier("test"), budget)

        assert ok is True
        assert stdout == "recovered"
        assert fake.call_count == 2

    def test_design_failure_does_not_retry(self, monkeypatch) -> None:
        budget = RetryBudget(l1_max_attempts=2, l2_max_attempts=3)
        fake = self._patch_agent(monkeypatch, side_effect=[(False, "design failed")])

        ok, _ = _invoke_with_retry("prompt", 1, _make_classifier("design"), budget)

        assert ok is False
        assert fake.call_count == 1

    def test_provider_rate_limit_propagates(self, monkeypatch) -> None:
        budget = RetryBudget(l1_max_attempts=2, l2_max_attempts=2)
        fake = self._patch_agent(
            monkeypatch,
            side_effect=ProviderRateLimitError("429"),
        )

        with pytest.raises(ProviderRateLimitError):
            _invoke_with_retry("prompt", 1, _make_classifier("test"), budget)

        assert fake.call_count == 1

    def test_provider_quota_propagates(self, monkeypatch) -> None:
        budget = RetryBudget(l1_max_attempts=2, l2_max_attempts=2)
        fake = self._patch_agent(
            monkeypatch,
            side_effect=ProviderQuotaError("quota"),
        )

        with pytest.raises(ProviderQuotaError):
            _invoke_with_retry("prompt", 1, _make_classifier("implement"), budget)

        assert fake.call_count == 1

    def test_budget_exhausted_returns_false(self, monkeypatch) -> None:
        budget = RetryBudget(l1_max_attempts=1, l2_max_attempts=2)
        fake = self._patch_agent(
            monkeypatch,
            side_effect=[
                (False, "fail 1"),
                (False, "fail 2"),
            ],
        )

        ok, _ = _invoke_with_retry("prompt", 1, _make_classifier("test"), budget)

        assert ok is False
        assert fake.call_count == 2


class TestStageSideEffects:
    """Retry wiring preserves existing post-invocation side effects."""

    def test_run_design_stage_writes_artifacts_on_success(
        self, tmp_path, monkeypatch
    ) -> None:
        from core.pipeline.stages import design as design_mod

        design_dir = tmp_path / "docs" / "designs"
        design_dir.mkdir(parents=True)
        design_file = design_dir / "1.md"
        design_file.write_text("# Real design spec\n")
        monkeypatch.setattr(design_mod, "DESIGN_SPEC_DIR", design_dir)

        with (
            mock.patch("core.pipeline.github.comments.gh_comment"),
            mock.patch("core.pipeline.retry.log_metrics"),
            mock.patch(
                "core.pipeline.prompts.assemble_stage_prompt",
                return_value="# Design prompt\n",
            ),
            mock.patch(
                "core.pipeline.retry._invoke_with_retry",
                return_value=(True, "ok"),
            ) as invoke_retry,
            mock.patch(
                "core.pipeline.artifacts_ops.write_design_artifacts"
            ) as write_artifacts,
        ):
            result = design_mod.run_design_stage(
                {"number": 1, "title": "Test", "body": ""}
            )

        assert result is True
        invoke_retry.assert_called_once()
        write_artifacts.assert_called_once()

    def test_run_test_subagent_locks_qa_tests_after_success(
        self, tmp_path, monkeypatch
    ) -> None:
        tests_dir = tmp_path / "tests" / "unit"
        tests_dir.mkdir(parents=True)
        qa_file = tests_dir / "test_qa.py"
        qa_file.write_text("def test_qa(): pass\n")

        monkeypatch.setattr(build_subagents, "PROJECT_ROOT", tmp_path)

        with (
            mock.patch.object(
                build_subagents, "_invoke_with_retry", return_value=(True, "")
            ),
            mock.patch.object(build_subagents, "gh_comment"),
            mock.patch.object(build_subagents, "log_metrics"),
            mock.patch.object(build_subagents, "_snapshot_tests_dir"),
            mock.patch.object(
                build_subagents,
                "_detect_new_tests",
                return_value=[str(qa_file.relative_to(tmp_path))],
            ),
            mock.patch.object(build_subagents, "_save_test_tracking"),
            mock.patch.object(build_subagents, "write_qa_tests"),
        ):
            result = build_subagents._run_test_subagent({"number": 1, "title": "Test"})

        assert result is True
        assert (qa_file.stat().st_mode & 0o777) == 0o444

    def test_run_implement_subagent_appends_qa_test_list(
        self, tmp_path, monkeypatch
    ) -> None:
        tests_dir = tmp_path / "tests" / "unit"
        tests_dir.mkdir(parents=True)
        qa_file = tests_dir / "test_qa.py"
        qa_file.write_text("def test_qa(): pass\n")
        rel_path = str(qa_file.relative_to(tmp_path))

        monkeypatch.setattr(build_subagents, "PROJECT_ROOT", tmp_path)

        captured_prompts: list[str] = []

        def fake_invoke_with_retry(prompt, issue_num, classifier, budget):
            captured_prompts.append(prompt)
            return True, ""

        with (
            mock.patch.object(
                build_subagents,
                "_invoke_with_retry",
                side_effect=fake_invoke_with_retry,
            ),
            mock.patch.object(build_subagents, "gh_comment"),
            mock.patch.object(build_subagents, "log_metrics"),
            mock.patch.object(
                build_subagents, "_load_test_tracking", return_value=[rel_path]
            ),
            mock.patch.object(
                build_subagents, "_resolve_existing_test_paths", return_value=[rel_path]
            ),
            mock.patch.object(
                build_subagents, "_assemble_subagent_prompt", return_value="BASE PROMPT"
            ),
        ):
            build_subagents._run_implement_subagent({"number": 1, "title": "Test"})

        assert captured_prompts
        assert rel_path in captured_prompts[-1]
        assert "QA-Written Test Files" in captured_prompts[-1]
