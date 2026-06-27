"""Tests for core.pipeline.stages.verify (C1.4c)."""

from __future__ import annotations


class TestVerifyStageAtNewPath:
    """C1.4c: VERIFY stage at new location."""

    def test_verify_stage_importable(self) -> None:
        from core.pipeline.stages.verify import VerifyStage

        assert VerifyStage is not None

    def test_verify_stage_inherits_from_stage(self) -> None:
        from core.pipeline.stages.base import Stage
        from core.pipeline.stages.verify import VerifyStage

        assert issubclass(VerifyStage, Stage)

    def test_verify_stage_name_is_verify(self) -> None:
        from core.pipeline.stages.verify import VerifyStage

        assert VerifyStage.name == "verify"

    def test_verify_stage_run_is_callable(self) -> None:
        from core.pipeline.stages.verify import VerifyStage

        stage = VerifyStage()
        assert callable(stage.run)
