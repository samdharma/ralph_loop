"""Tests for core.pipeline.stages.design (C1.4a)."""

from __future__ import annotations


class TestDesignStageAtNewPath:
    """C1.4a: DESIGN stage at new location."""

    def test_design_stage_importable(self) -> None:
        from core.pipeline.stages.design import DesignStage

        assert DesignStage is not None

    def test_design_stage_inherits_from_stage(self) -> None:
        from core.pipeline.stages.base import Stage
        from core.pipeline.stages.design import DesignStage

        assert issubclass(DesignStage, Stage)

    def test_design_stage_name_is_design(self) -> None:
        from core.pipeline.stages.design import DesignStage

        assert DesignStage.name == "design"

    def test_design_stage_run_is_callable(self) -> None:
        from core.pipeline.stages.design import DesignStage

        stage = DesignStage()
        assert callable(stage.run)
