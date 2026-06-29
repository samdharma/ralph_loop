"""Smoke integration tests for Ralph v3.1.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §8.2, integration tests live under
`tests/integration/`. They run against mocked `gh` and `git` (per spec §8.4)
and exercise full pipeline paths.

Phase A adds minimal smoke coverage; subsequent phases extend this with
artifact handoff, retry budgets, idempotency, worktree isolation, etc.
"""

import json
import sys
from pathlib import Path

# Make core/ importable without installing Ralph.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))


def test_ralph_migrate_dry_run_returns_valid_json(tmp_path, monkeypatch):
    """End-to-end: ralph migrate --dry-run on a v3-format project returns a JSON-serializable report."""
    monkeypatch.chdir(tmp_path)
    # Set up a v3-format .ralph/ state directory.
    ralph_dir = tmp_path / ".ralph"
    ralph_dir.mkdir()
    (ralph_dir / "issue-1-tests.json").write_text(
        json.dumps({"issue": 1, "tests": ["tests/unit/test_x.py"]})
    )

    # Import + run migrate.
    import migrate  # type: ignore[import-not-found]

    report = migrate.migrate(dry_run=True)
    # Report is JSON-serializable.
    json.dumps(report)
    assert "actions" in report
    # Dry-run must not modify the filesystem.
    assert (ralph_dir / "issue-1-tests.json").exists()
    assert not (ralph_dir / "migration-archive").exists()


def test_ralph_validate_classify_exit_codes():
    """verify that all exit codes mentioned in spec §10.1 A1 are classified."""
    import validate  # type: ignore[import-not-found]

    for code, expected_class in [
        (0, "success"),
        (1, "test_failure"),
        (124, "timeout"),
        (137, "interrupted"),
        (143, "interrupted"),
    ]:
        result = validate.classify_pytest_exit_code(code)
        assert (
            result.classification == expected_class
        ), f"Exit code {code} should classify as {expected_class}, got {result.classification}"


def test_artifact_writer_round_trip(tmp_path, monkeypatch):
    """End-to-end: write all four artifact files, read them back, contents match."""
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

    from core.pipeline.agents.artifacts import (  # type: ignore[import-not-found]
        write_acceptance_criteria,
        write_design,
        write_files_in_scope,
        write_qa_tests,
    )

    write_design(1, "# design for #1", project_root=tmp_path)
    write_files_in_scope(1, ["a.py", "b.py"], project_root=tmp_path)
    write_acceptance_criteria(
        1, [{"id": "AC1", "criterion": "tests pass"}], project_root=tmp_path
    )
    write_qa_tests(1, ["tests/test_a.py::test_x"], project_root=tmp_path)

    artifact_dir = tmp_path / ".ralph" / "issues" / "1" / "artifacts"
    assert (artifact_dir / "design.md").read_text() == "# design for #1"
    assert json.loads((artifact_dir / "files_in_scope.json").read_text()) == [
        "a.py",
        "b.py",
    ]
    assert json.loads((artifact_dir / "acceptance_criteria.json").read_text()) == [
        {"id": "AC1", "criterion": "tests pass"}
    ]
    assert json.loads((artifact_dir / "qa_tests_to_pass.json").read_text()) == [
        "tests/test_a.py::test_x"
    ]
