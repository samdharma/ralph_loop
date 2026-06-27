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
