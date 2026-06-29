#!/usr/bin/env bash
# scripts/release.sh — Tag, push, and publish a Ralph release.
#
# Per docs/IMPROVEMENT_ROADMAP_SPEC.md §5.5 and §10.3 C2.
#
# Usage:
#     scripts/release.sh <version>     # e.g. scripts/release.sh 3.1.2
#     make release PART=patch          # uses version_bump.py first
#
# Behavior:
#   1. Tag the current commit with ``ralph-v<version>``
#   2. Push the tag to origin
#   3. Create a GitHub release via ``gh release create --generate-notes``
#
# Pre-conditions:
#   - Working tree is clean (no uncommitted changes)
#   - On the correct branch (ralph-v3.1 for v3.1.x releases)
#   - gh CLI is authenticated
#   - origin remote is set and reachable

set -euo pipefail

VERSION="${1:-}"
REPO_ROOT="$(git rev-parse --show-toplevel)"

if [[ -z "$VERSION" ]]; then
    echo "Usage: scripts/release.sh <version>" >&2
    echo "  e.g. scripts/release.sh 3.1.2" >&2
    exit 1
fi

TAG="ralph-v${VERSION}"

# Pre-flight checks
if [[ -n "$(git status --porcelain)" ]]; then
    echo "✗ Working tree is not clean. Commit or stash changes first." >&2
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "✗ gh CLI not found. Install from https://cli.github.com/" >&2
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "✗ gh is not authenticated. Run 'gh auth login'." >&2
    exit 1
fi

# Check tag does not already exist (idempotent — refuses to overwrite)
if git tag --list "$TAG" | grep -q "^${TAG}$"; then
    echo "✗ Tag ${TAG} already exists locally." >&2
    echo "  Delete with 'git tag -d ${TAG}' and re-run, or pick a new version." >&2
    exit 1
fi

# Tag, push, release
echo "[ralph] Tagging ${TAG}..."
git tag "$TAG" -m "Ralph v${VERSION} — Phase complete"

echo "[ralph] Pushing ${TAG} to origin..."
git push origin "$TAG"

echo "[ralph] Creating GitHub release ${TAG}..."
gh release create "$TAG" --generate-notes --title "Ralph v${VERSION}"

echo ""
echo "✓ Released ${TAG}"
echo "  View at: $(gh release view "$TAG" --json url -q .url)"