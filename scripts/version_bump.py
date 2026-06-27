#!/usr/bin/env python3
"""Bump Ralph version across the three tracked locations.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §5.5:
- pyproject.toml        → [project].version
- core/__init__.py      → __version__
- bin/ralph             → cmd_version output

Usage:
    python scripts/version_bump.py <major|minor|patch>
    make version-bump PART=minor
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PYPROJECT = REPO_ROOT / "pyproject.toml"
CORE_INIT = REPO_ROOT / "core" / "__init__.py"
RALPH_BIN = REPO_ROOT / "bin" / "ralph"


def _current_version() -> str:
    """Read the current version from pyproject.toml."""
    text = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        print(f"ERROR: no version found in {PYPROJECT}", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def _next_version(current: str, part: str) -> str:
    """Compute the next version given a bump part."""
    try:
        major, minor, patch = (int(x) for x in current.split("."))
    except ValueError:
        print(f"ERROR: cannot parse version {current!r}", file=sys.stderr)
        sys.exit(1)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    print(f"ERROR: part must be one of major/minor/patch; got {part!r}", file=sys.stderr)
    sys.exit(1)


def _update_pyproject(new_version: str) -> None:
    text = PYPROJECT.read_text()
    new_text = re.sub(
        r'^(version\s*=\s*)"[^"]+"',
        rf'\1"{new_version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(new_text)


def _update_core_init(new_version: str) -> None:
    text = CORE_INIT.read_text() if CORE_INIT.exists() else ""
    if re.search(r"^__version__\s*=", text, re.MULTILINE):
        new_text = re.sub(
            r'^(__version__\s*=\s*)"[^"]+"',
            rf'\1"{new_version}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        new_text = text.rstrip() + f'\n\n__version__ = "{new_version}"\n'
    CORE_INIT.write_text(new_text)


def _update_bin_ralph(new_version: str) -> None:
    text = RALPH_BIN.read_text()
    new_text = re.sub(
        r'(echo\s+"ralph\s+v)[\d.]+(")',
        rf'\g<1>{new_version}\g<2>',
        text,
        count=1,
    )
    RALPH_BIN.write_text(new_text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump Ralph version.")
    parser.add_argument("part", choices=["major", "minor", "patch"], help="Bump part")
    args = parser.parse_args()

    current = _current_version()
    next_ver = _next_version(current, args.part)

    _update_pyproject(next_ver)
    _update_core_init(next_ver)
    _update_bin_ralph(next_ver)

    print(f"Bumped version: {current} -> {next_ver}")
    print("Run: git add pyproject.toml core/__init__.py bin/ralph && git commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())