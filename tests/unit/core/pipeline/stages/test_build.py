"""Tests for core.pipeline.stages.build (C1.4b)."""

from __future__ import annotations


class TestBuildStageAtNewPath:
    """C1.4b: BUILD stage at new location."""

    def test_build_stage_importable(self) -> None:
        from core.pipeline.stages.build import BuildStage

        assert BuildStage is not None

    def test_build_stage_inherits_from_stage(self) -> None:
        from core.pipeline.stages.base import Stage
        from core.pipeline.stages.build import BuildStage

        assert issubclass(BuildStage, Stage)

    def test_build_stage_name_is_build(self) -> None:
        from core.pipeline.stages.build import BuildStage

        assert BuildStage.name == "build"

    def test_build_stage_run_is_callable(self) -> None:
        from core.pipeline.stages.build import BuildStage

        stage = BuildStage()
        assert callable(stage.run)
