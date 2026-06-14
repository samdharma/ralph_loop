#!/usr/bin/env python3
"""
Ralph v3 — TEST_MAP.yaml Auto-Generator

Scans the project source and test directories and generates a
config/TEST_MAP.yaml mapping source files to their corresponding
test files based on naming conventions.

Conventions detected:
    src/my_project/module.py          → tests/unit/test_module.py
    src/my_project/sub/module.py      → tests/unit/test_sub_module.py
    src/my_project/module.py          → tests/integration/test_module_integration.py

Also maps __init__.py files and handles common suffixes (_test, _spec, etc.)

Usage:
    ralph generate-test-map              # Generate TEST_MAP.yaml
    ralph generate-test-map --dry-run     # Preview only, don't write
    python core/generate_test_map.py      # Direct invocation
"""

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
SRC_DIR = PROJECT_ROOT / "src"
TEST_DIR = PROJECT_ROOT / "tests"
TEST_MAP_PATH = PROJECT_ROOT / "config" / "TEST_MAP.yaml"

TEST_SUFFIXES = [
    "test_",
    "_test",
    "test",
    "spec_",
    "_spec",
]


def find_python_files(directory: Path) -> list[Path]:
    """Recursively find all .py files in a directory, relative to PROJECT_ROOT."""
    if not directory.exists():
        return []
    files = []
    for f in directory.rglob("*.py"):
        rel = f.relative_to(PROJECT_ROOT)
        files.append(rel)
    return sorted(files)


def module_name_from_path(path: Path) -> str:
    """Extract module name from a source file path.
    src/my_project/order_book.py → my_project.order_book
    """
    parts = list(path.parts)
    # Remove leading src/ and trailing .py
    if parts[0] == "src":
        parts = parts[1:]
    name = "/".join(parts)
    if name.endswith(".py"):
        name = name[:-3]
    # Handle __init__ files
    if name.endswith("__init__"):
        name = name[:-9] or name  # strip trailing __init__
    name = name.replace("/", ".")
    return name


def guess_test_file(source_rel: Path) -> list[str]:
    """Given a source file, guess possible test file paths (relative to PROJECT_ROOT)."""
    candidates = []
    source_name = source_rel.stem  # filename without .py
    source_parts = list(source_rel.parts)

    # Remove leading src/
    if source_parts[0] == "src":
        source_parts = source_parts[1:]

    # Skip __init__.py — usually tested via package-level tests
    if source_name == "__init__":
        return []

    # Build dotted name for subpackage paths
    sub_path = "/".join(source_parts[:-1]) if len(source_parts) > 1 else ""

    # Candidate 1: tests/unit/test_<module>.py
    if sub_path:
        candidates.append(f"tests/unit/test_{sub_path.replace('/', '_')}_{source_name}.py")
    candidates.append(f"tests/unit/test_{source_name}.py")

    # Candidate 2: tests/unit/<module>_test.py
    if sub_path:
        candidates.append(f"tests/unit/{sub_path.replace('/', '_')}_{source_name}_test.py")
    candidates.append(f"tests/unit/{source_name}_test.py")

    # Candidate 3: tests/integration/test_<module>_integration.py
    if sub_path:
        candidates.append(f"tests/integration/test_{sub_path.replace('/', '_')}_{source_name}_integration.py")
    candidates.append(f"tests/integration/test_{source_name}_integration.py")

    # Filter to only existing files
    existing = [c for c in candidates if (PROJECT_ROOT / c).exists()]
    return existing


def generate_test_map(dry_run: bool = False) -> dict:
    """
    Generate TEST_MAP.yaml contents from project structure.
    Returns the mappings dict.
    """
    source_files = find_python_files(SRC_DIR)
    test_files = {str(f) for f in find_python_files(TEST_DIR)}

    mappings = []
    unmatched = 0

    for src_file in source_files:
        tests = guess_test_file(src_file)
        if tests:
            mappings.append({
                "source": str(src_file),
                "tests": list(sorted(set(tests))),
            })
        else:
            unmatched += 1

    # Default tests: run unit/ if nothing matches
    default_tests = []
    if (TEST_DIR / "unit").exists():
        default_tests.append("tests/unit/")

    result = {
        "mappings": mappings,
        "default_tests": default_tests,
    }

    return result


def format_yaml(data: dict) -> str:
    """Format TEST_MAP data as readable YAML."""
    lines = [
        "# Ralph v3 — Test Map (auto-generated)",
        "# Maps source files to their corresponding test paths.",
        "# Used by `ralph validate --tier=targeted` to run only affected tests.",
        "#",
        f"# Generated from {len(data['mappings'])} source files.",
        "# Regenerate: ralph generate-test-map",
        "",
        "mappings:",
    ]

    for m in data["mappings"]:
        lines.append(f'  - source: "{m["source"]}"')
        if len(m["tests"]) == 1:
            lines.append(f'    tests: ["{m["tests"][0]}"]')
        else:
            lines.append("    tests: [")
            for t in m["tests"]:
                lines.append(f'      "{t}",')
            lines.append("    ]")

    lines.append("")
    lines.append("default_tests:")
    for dt in data.get("default_tests", []):
        lines.append(f'  - "{dt}"')

    if not data.get("default_tests"):
        lines.append("  - \"tests/unit/\"")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate TEST_MAP.yaml from project structure"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the generated TEST_MAP without writing",
    )
    args = parser.parse_args()

    print("[ralph] Scanning project for source and test files...")

    source_files = find_python_files(SRC_DIR)
    test_files = find_python_files(TEST_DIR)

    print(f"[ralph]   Source files: {len(source_files)}")
    print(f"[ralph]   Test files:  {len(test_files)}")

    if not source_files:
        print("[ralph] No source files found in src/. Skipping.")
        return 0

    data = generate_test_map(dry_run=args.dry_run)
    yaml_text = format_yaml(data)

    mapped = len(data["mappings"])
    total_tests_mapped = sum(len(m["tests"]) for m in data["mappings"])

    print(f"[ralph]   Mappings generated: {mapped}")
    print(f"[ralph]   Test targets mapped: {total_tests_mapped}")

    if args.dry_run:
        print("\n--- PREVIEW ---")
        print(yaml_text)
        print("--- END PREVIEW ---")
        print("\n[ralph] Dry run — not written. Use without --dry-run to save.")
        return 0

    TEST_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEST_MAP_PATH.write_text(yaml_text)
    print(f"[ralph] TEST_MAP.yaml written to {TEST_MAP_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
