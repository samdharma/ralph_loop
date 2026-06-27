"""Tests for the artifact directory writer module.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.2 and §10.1 A3:

The per-issue artifact directory `.ralph/issues/<N>/artifacts/` is the
contract between stages (DESIGN writes, IMPLEMENT reads). Each artifact
file has a fixed name and JSON/Markdown content shape.

Tests cover the four write_* functions and idempotency.
"""

import json
import sys
from pathlib import Path

import pytest

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "core"))

from core.pipeline.agents import artifacts  # noqa: E402


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PROJECT_ROOT at tmp_path so artifacts land in tmp_path/.ralph/."""
    monkeypatch.setattr(artifacts, "PROJECT_ROOT", tmp_path)
    return tmp_path


def test_write_design_creates_design_md(project_root: Path) -> None:
    """write_design(issue_num, design_text) creates design.md with the given content."""
    from core.pipeline.agents.artifacts import (
        write_design,  # type: ignore[import-not-found]
    )

    path = write_design(1, "# Issue #1 design\n\nApproach: TDD.")
    assert path.name == "design.md"
    assert path.read_text() == "# Issue #1 design\n\nApproach: TDD."
    assert path.parent == project_root / ".ralph" / "issues" / "1" / "artifacts"


def test_write_files_in_scope_creates_json(project_root: Path) -> None:
    """write_files_in_scope(issue_num, paths_list) creates files_in_scope.json containing the list."""
    from core.pipeline.agents.artifacts import (
        write_files_in_scope,  # type: ignore[import-not-found]
    )

    paths = ["src/foo.py", "tests/unit/test_foo.py"]
    out = write_files_in_scope(1, paths)
    assert out.name == "files_in_scope.json"
    loaded = json.loads(out.read_text())
    assert loaded == paths


def test_write_acceptance_criteria_creates_json(project_root: Path) -> None:
    """write_acceptance_criteria(issue_num, ac_list) creates acceptance_criteria.json with each AC as {id, criterion}."""
    from core.pipeline.agents.artifacts import (
        write_acceptance_criteria,  # type: ignore[import-not-found]
    )

    ac = [
        {"id": "AC1", "criterion": "tests pass"},
        {"id": "AC2", "criterion": "lint clean"},
    ]
    out = write_acceptance_criteria(1, ac)
    assert out.name == "acceptance_criteria.json"
    loaded = json.loads(out.read_text())
    assert loaded == ac
    assert all("id" in item and "criterion" in item for item in loaded)


def test_write_qa_tests_creates_json(project_root: Path) -> None:
    """write_qa_tests(issue_num, qa_tests) creates qa_tests_to_pass.json."""
    from core.pipeline.agents.artifacts import (
        write_qa_tests,  # type: ignore[import-not-found]
    )

    qa = ["tests/unit/test_foo.py::test_a", "tests/unit/test_foo.py::test_b"]
    out = write_qa_tests(1, qa)
    assert out.name == "qa_tests_to_pass.json"
    loaded = json.loads(out.read_text())
    assert loaded == qa


def test_write_design_is_idempotent(project_root: Path) -> None:
    """Writing the same design twice produces identical filesystem state."""
    from core.pipeline.agents.artifacts import (
        write_design,  # type: ignore[import-not-found]
    )

    write_design(1, "first")
    before = sorted(p.name for p in project_root.rglob("*"))
    write_design(1, "second")  # overwrites
    after = sorted(p.name for p in project_root.rglob("*"))
    assert before == after
    # The content is the second write
    design = project_root / ".ralph" / "issues" / "1" / "artifacts" / "design.md"
    assert design.read_text() == "second"


def test_write_files_in_scope_is_idempotent(project_root: Path) -> None:
    """Writing the same files_in_scope twice produces identical filesystem state."""
    from core.pipeline.agents.artifacts import (
        write_files_in_scope,  # type: ignore[import-not-found]
    )

    write_files_in_scope(1, ["a.py"])
    write_files_in_scope(1, ["b.py"])
    loaded = json.loads(
        (
            project_root
            / ".ralph"
            / "issues"
            / "1"
            / "artifacts"
            / "files_in_scope.json"
        ).read_text()
    )
    assert loaded == ["b.py"]


def test_distinct_issues_get_distinct_directories(project_root: Path) -> None:
    """Different issue numbers get separate artifact directories."""
    from core.pipeline.agents.artifacts import (
        write_design,  # type: ignore[import-not-found]
    )

    write_design(1, "issue 1 design")
    write_design(2, "issue 2 design")
    assert (
        project_root / ".ralph" / "issues" / "1" / "artifacts" / "design.md"
    ).exists()
    assert (
        project_root / ".ralph" / "issues" / "2" / "artifacts" / "design.md"
    ).exists()


# ─────────────────────────────────────────────────────────
# C1.5d — artifacts at new path (spec §6.1, §6.2, §10.3 C1)
# ─────────────────────────────────────────────────────────


class TestArtifactsAtNewPath:
    """C1.5d: artifacts module is at core/pipeline/agents/artifacts.py
    (created in A-020) and the engine wires through it.

    These tests verify the module is at the new path AND that all
    four write_* functions continue to work. (Idempotency is
    covered by the A-020 tests above.)
    """

    def test_write_design_at_new_path(self, project_root: Path) -> None:
        """write_design creates the file at the new path."""
        from core.pipeline.agents.artifacts import write_design

        write_design(99, "design text for issue 99")
        assert (
            project_root / ".ralph" / "issues" / "99" / "artifacts" / "design.md"
        ).exists()

    def test_write_files_in_scope_at_new_path(self, project_root: Path) -> None:
        """write_files_in_scope creates files_in_scope.json."""
        from core.pipeline.agents.artifacts import write_files_in_scope

        write_files_in_scope(99, ["a.py", "b.py"])
        path = project_root / ".ralph" / "issues" / "99" / "artifacts" / "files_in_scope.json"
        assert path.exists()

    def test_write_acceptance_criteria_at_new_path(self, project_root: Path) -> None:
        """write_acceptance_criteria creates acceptance_criteria.json."""
        from core.pipeline.agents.artifacts import write_acceptance_criteria

        write_acceptance_criteria(99, [{"id": "AC1", "criterion": "x"}])
        path = (
            project_root
            / ".ralph"
            / "issues"
            / "99"
            / "artifacts"
            / "acceptance_criteria.json"
        )
        assert path.exists()

    def test_write_qa_tests_at_new_path(self, project_root: Path) -> None:
        """write_qa_tests creates qa_tests_to_pass.json."""
        from core.pipeline.agents.artifacts import write_qa_tests

        write_qa_tests(99, ["tests/unit/test_x.py"])
        path = (
            project_root
            / ".ralph"
            / "issues"
            / "99"
            / "artifacts"
            / "qa_tests_to_pass.json"
        )
        assert path.exists()
