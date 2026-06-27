"""Tests for core.pipeline.checkpoint (C1.7a)."""

from __future__ import annotations


class TestCheckpointAtNewPath:
    """C1.7a: checkpoint helpers at new location."""

    def test_save_checkpoint_importable(self) -> None:
        from core.pipeline.checkpoint import save_checkpoint

        assert callable(save_checkpoint)

    def test_clear_checkpoint_importable(self) -> None:
        from core.pipeline.checkpoint import clear_checkpoint

        assert callable(clear_checkpoint)

    def test_recover_from_crash_importable(self) -> None:
        from core.pipeline.checkpoint import recover_from_crash

        assert callable(recover_from_crash)

    def test_checkpoint_state_pydantic_model(self) -> None:
        """CheckpointState is a Pydantic model per spec §6.1."""
        from core.schemas.checkpoint import CheckpointState

        cs = CheckpointState(
            issue_num=42,
            stage="build",
            pre_sha="abc1234",
            run_id="20260101T0000-deadbeef",
        )
        assert cs.issue_num == 42
        assert cs.stage == "build"
        assert cs.pre_sha == "abc1234"
        assert cs.run_id == "20260101T0000-deadbeef"
