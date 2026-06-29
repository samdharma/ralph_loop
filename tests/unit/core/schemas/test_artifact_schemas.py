"""Tests for the artifact Pydantic schemas.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §4.2 and §6.2.

Covers:

- Construction and validation of each artifact model.
- Serialization round-trips.
- Forbidden-extra rejection.
- Integration with the writer functions in
  :mod:`core.pipeline.agents.artifacts`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "core"))

from core.pipeline.agents import artifacts as artifact_writers  # noqa: E402
from core.schemas.artifacts import (  # noqa: E402
    AcceptanceCriterion,
    DesignArtifact,
    ImplementationArtifact,
    TestArtifact,
)


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PROJECT_ROOT at tmp_path so artifacts land in tmp_path/.ralph/."""
    monkeypatch.setattr(artifact_writers, "PROJECT_ROOT", tmp_path)
    return tmp_path


class TestAcceptanceCriterion:
    """Unit tests for :class:`AcceptanceCriterion`."""

    def test_valid_criterion(self) -> None:
        """A dict with id and criterion validates."""
        ac = AcceptanceCriterion(id="AC1", criterion="tests pass")
        assert ac.id == "AC1"
        assert ac.criterion == "tests pass"

    def test_missing_fields_raise(self) -> None:
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            AcceptanceCriterion.model_validate({"id": "AC1"})

    def test_serialization_round_trip(self) -> None:
        """model_dump -> model_validate returns an equal instance."""
        original = AcceptanceCriterion(id="AC2", criterion="lint clean")
        payload = original.model_dump()
        restored = AcceptanceCriterion.model_validate(payload)
        assert restored == original


class TestDesignArtifact:
    """Unit tests for :class:`DesignArtifact`."""

    def test_minimal_design_artifact(self) -> None:
        """A DesignArtifact can be constructed with just issue_num and design_text."""
        design = DesignArtifact(issue_num=42, design_text="# Design")
        assert design.issue_num == 42
        assert design.design_text == "# Design"
        assert design.files_in_scope == []
        assert design.acceptance_criteria == []

    def test_full_design_artifact(self) -> None:
        """All fields are accepted and serialized."""
        design = DesignArtifact(
            issue_num=1,
            design_text="# Issue #1",
            files_in_scope=["src/foo.py"],
            acceptance_criteria=[AcceptanceCriterion(id="AC1", criterion="tests pass")],
        )
        payload = design.model_dump()
        assert payload["issue_num"] == 1
        assert payload["files_in_scope"] == ["src/foo.py"]
        assert payload["acceptance_criteria"] == [
            {"id": "AC1", "criterion": "tests pass"}
        ]

    def test_extra_fields_forbidden(self) -> None:
        """Extra keys are rejected."""
        with pytest.raises(ValidationError):
            DesignArtifact(issue_num=1, design_text="x", run_id="abc")


class TestTestArtifact:
    """Unit tests for :class:`TestArtifact`."""

    def test_default_qa_tests(self) -> None:
        """qa_tests defaults to an empty list."""
        test = TestArtifact(issue_num=1)
        assert test.qa_tests == []

    def test_with_qa_tests(self) -> None:
        """qa_tests accepts a list of pytest node IDs."""
        test = TestArtifact(
            issue_num=1,
            qa_tests=["tests/unit/test_foo.py::test_a"],
        )
        assert test.qa_tests == ["tests/unit/test_foo.py::test_a"]


class TestImplementationArtifact:
    """Unit tests for :class:`ImplementationArtifact`."""

    def test_defaults(self) -> None:
        """All fields have sensible defaults."""
        impl = ImplementationArtifact(issue_num=1)
        assert impl.summary == ""
        assert impl.files_changed == []
        assert impl.tests_added == []

    def test_full_artifact(self) -> None:
        """All fields are accepted and serialized."""
        impl = ImplementationArtifact(
            issue_num=1,
            summary="Added feature X",
            files_changed=["src/foo.py"],
            tests_added=["tests/unit/test_foo.py"],
        )
        payload = impl.model_dump()
        assert payload == {
            "issue_num": 1,
            "summary": "Added feature X",
            "files_changed": ["src/foo.py"],
            "tests_added": ["tests/unit/test_foo.py"],
        }


class TestArtifactWriterRoundTrip:
    """Round-trip tests between schema models and writer functions."""

    def test_write_and_read_design_artifact(self, project_root: Path) -> None:
        """write_design_artifact -> read_design_artifact returns an equal model."""
        design = DesignArtifact(
            issue_num=7,
            design_text="# Issue #7\n\nApproach: TDD.",
            files_in_scope=["src/foo.py", "tests/unit/test_foo.py"],
            acceptance_criteria=[
                AcceptanceCriterion(id="AC1", criterion="tests pass"),
                AcceptanceCriterion(id="AC2", criterion="lint clean"),
            ],
        )
        artifact_writers.write_design_artifact(design)
        restored = artifact_writers.read_design_artifact(7)
        assert restored == design

    def test_write_and_read_test_artifact(self, project_root: Path) -> None:
        """write_test_artifact -> read_test_artifact returns an equal model."""
        test = TestArtifact(
            issue_num=7,
            qa_tests=["tests/unit/test_foo.py::test_a"],
        )
        artifact_writers.write_test_artifact(test)
        restored = artifact_writers.read_test_artifact(7)
        assert restored == test

    def test_acceptance_criteria_validation_rejects_bad_input(
        self, project_root: Path
    ) -> None:
        """write_acceptance_criteria raises when an AC dict is malformed."""
        with pytest.raises(ValidationError):
            artifact_writers.write_acceptance_criteria(
                1, [{"id": "AC1", "criterion": "ok"}, {"id": "AC2"}]
            )

    def test_read_missing_design_artifact_is_empty(self, project_root: Path) -> None:
        """read_design_artifact tolerates a missing artifact directory."""
        restored = artifact_writers.read_design_artifact(99)
        assert restored == DesignArtifact(
            issue_num=99,
            design_text="",
            files_in_scope=[],
            acceptance_criteria=[],
        )

    def test_write_acceptance_criteria_normalizes_extra_keys(
        self, project_root: Path
    ) -> None:
        """Extra keys in an AC dict are stripped during validation."""
        path = artifact_writers.write_acceptance_criteria(
            1, [{"id": "AC1", "criterion": "x", "extra": "ignored"}]
        )
        loaded = json.loads(path.read_text())
        assert loaded == [{"id": "AC1", "criterion": "x"}]
