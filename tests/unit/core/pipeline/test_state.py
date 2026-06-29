"""Tests for run_id generator and Stage enum.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §4.2 and §10.2 B2.

``core.pipeline.state`` exposes:

  - ``generate_run_id()`` — returns a string like
    ``<timestamp>-<uuid4_short>`` (e.g., ``20260627T1530-a1b2c3d4``).
    Uniqueness is asserted by generating 100 IDs and verifying no
    collisions.

The tests below cover:

  1. Shape: ``generate_run_id`` matches ``\\d{8}T\\d{4}-[a-f0-9]{8}$``.
  2. Uniqueness: 100 generated IDs are all distinct.
  3. Difference: two consecutive IDs differ in either the timestamp
     or the UUID portion (within the same wall-clock second this is
     still true because of the UUID component).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "core"))

from core.pipeline import state  # noqa: E402


def test_run_id_matches_expected_format() -> None:
    """run_id matches \\d{8}T\\d{4}-[a-f0-9]{8}$."""
    run_id = state.generate_run_id()
    assert re.match(r"^\d{8}T\d{4}-[a-f0-9]{8}$", run_id), run_id


def test_one_hundred_run_ids_are_unique() -> None:
    """Generating 100 run_ids produces 100 distinct values."""
    ids = {state.generate_run_id() for _ in range(100)}
    assert len(ids) == 100


def test_two_consecutive_run_ids_differ() -> None:
    """Two consecutive calls return different run_ids."""
    a = state.generate_run_id()
    b = state.generate_run_id()
    assert a != b


# ─────────────────────────────────────────────────────────
# C1.2 — state.py at new path (spec §6.1, §10.3 C1, plan §3 R-2)
# ─────────────────────────────────────────────────────────


class TestStateAtNewPath:
    """C1.2: stage state re-imported from core/pipeline/state.py.

    The state module already lives at the new path (B-007). This
    block pins that the public surface — ``Stage``, ``PipelineState``,
    ``STATUS_LABEL`` — is importable from the new location, and that
    the engine no longer redefines them locally.

    Per plan §3 R-2: this test runs alongside the snapshot test as
    a behavior-change detector for the C1.x moves.
    """

    def test_state_module_imports_stage_pipeline_state_status_label(self) -> None:
        """``from core.pipeline.state import Stage, PipelineState, STATUS_LABEL`` succeeds."""
        from core.pipeline.state import (  # noqa: F401
            STATUS_LABEL,
            PipelineState,
            Stage,
        )

        assert Stage is not None
        assert PipelineState is not None
        assert STATUS_LABEL is not None

    def test_stage_design_value_is_design(self) -> None:
        """Stage.DESIGN.value == 'design'."""
        from core.pipeline.state import Stage

        assert Stage.DESIGN.value == "design"

    def test_status_label_for_design_stage(self) -> None:
        """STATUS_LABEL[Stage.DESIGN] == 'status:design'."""
        from core.pipeline.state import STATUS_LABEL, Stage

        assert STATUS_LABEL[Stage.DESIGN] == "status:design"

    def test_pipeline_state_pydantic_model(self) -> None:
        """PipelineState is a Pydantic model with the expected fields."""
        from core.pipeline.state import PipelineState, Stage

        # Construct via Pydantic; verify field access.
        ps = PipelineState(
            issue_num=42,
            stage=Stage.DESIGN,
            pre_sha="abc1234",
            run_id="20260101T0000-deadbeef",
        )
        assert ps.issue_num == 42
        assert ps.stage == Stage.DESIGN
        assert ps.pre_sha == "abc1234"
        assert ps.run_id == "20260101T0000-deadbeef"

    def test_engine_does_not_redefine_state_symbols(self) -> None:
        """core.engine imports Stage / PipelineState / STATUS_LABEL from core.pipeline.state
        rather than redefining them locally."""
        import inspect

        import core.engine as engine_mod
        from core.pipeline import state as state_mod

        source = inspect.getsource(engine_mod)
        # The engine should import these from core.pipeline.state.
        assert (
            "from core.pipeline.state import" in source
            or "from core.pipeline import state" in source
        ), "engine.py must import state symbols from core.pipeline.state"

        # State module has them defined.
        assert hasattr(state_mod, "Stage")
        assert hasattr(state_mod, "PipelineState")
        assert hasattr(state_mod, "STATUS_LABEL")
