#!/usr/bin/env bash
# Ralph v3.1 — Installer
#
# Usage (new in v3.1, replaces the v3 curl|bash flow):
#   git clone https://github.com/samdharma/Ralph_loop
#   cd Ralph_loop
#   git checkout ralph-v3.1
#   ./scripts/install.sh
#
# Or from a local clone:
#   bash scripts/install.sh [--help]
#
# Installs ralph CLI to /usr/local/bin (or ~/.local/bin) and sets RALPH_HOME.
# Preserves the bash dispatcher bin/ralph per spec §3.7 (only v3.2 may drop it).
# Validates all prerequisites before installation.
#
# Prerequisites (per spec §4.1):
#   - git 2.30+
#   - gh 2.0+ (GitHub CLI)
#   - python 3.10+
#   - pi or kimi (one of the AI agent CLIs)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${BOLD}→${NC} $1"; }

MISSING=()
WARNINGS=()

RALPH_HOME="${RALPH_HOME:-$HOME/.ralph}"

# Determine the source directory (where this script lives)
# When run via `curl ... | bash`, BASH_SOURCE may be unset.
SCRIPT_SOURCE="${BASH_SOURCE[0]:-}"
if [[ -n "${SCRIPT_SOURCE}" && -f "${SCRIPT_SOURCE}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_SOURCE}")" && pwd)"
    REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
    REPO_DIR=""
fi

# Derive version from pyproject.toml, git tags, or fallback to 3.1.0
if [[ -n "${REPO_DIR}" && -f "${REPO_DIR}/pyproject.toml" ]]; then
    RALPH_VERSION=$(grep -oE '^version = "[^"]+"' "${REPO_DIR}/pyproject.toml" | head -1 | sed -E 's/version = "([^"]+)"/\1/')
elif command -v git &>/dev/null && git describe --tags --always &>/dev/null; then
    RALPH_VERSION=$(git describe --tags --always)
fi
RALPH_VERSION="${RALPH_VERSION:-3.1.0}"

echo "╔══════════════════════════════════════════╗"
echo "║   Ralph v3.1 — Automated Build System    ║"
echo "║   Installer v${RALPH_VERSION}                     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# --help prints usage and exits 0.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,30p' "$0"
    exit 0
fi

# ──────────────────────────────────────────────────────────────
# Step 1: Prerequisite Checks
# ──────────────────────────────────────────────────────────────
echo "Checking prerequisites..."
echo ""

# Check bash version
BASH_MAJOR="${BASH_VERSINFO[0]:-0}"
if [[ "${BASH_MAJOR}" -ge 4 ]]; then
    pass "bash ${BASH_VERSION} (4+ required)"
else
    fail "bash ${BASH_VERSION} — version 4+ required"
    MISSING+=("bash 4+ — upgrade your shell (macOS: brew install bash)")
fi

# Check git
if command -v git &>/dev/null; then
    GIT_VER=$(git --version 2>/dev/null | head -1)
    pass "git (${GIT_VER})"
else
    fail "git — not found in PATH"
    MISSING+=("git — https://git-scm.com/downloads (macOS: brew install git)")
fi

# Check gh (GitHub CLI)
if command -v gh &>/dev/null; then
    GH_VER=$(gh --version 2>/dev/null | head -1)
    pass "gh (${GH_VER})"
else
    fail "gh — GitHub CLI not found in PATH"
    MISSING+=("gh — https://cli.github.com/ (macOS: brew install gh)")
fi

# Check Python 3.10+
PYTHON_CMD=""
for py in python3 python; do
    if command -v "${py}" &>/dev/null; then
        PY_VER=$("${py}" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "0.0")
        PY_MAJOR=$(echo "${PY_VER}" | cut -d. -f1)
        PY_MINOR=$(echo "${PY_VER}" | cut -d. -f2)
        if [[ "${PY_MAJOR}" -ge 3 && "${PY_MINOR}" -ge 10 ]]; then
            PYTHON_CMD="${py}"
            pass "Python ${PY_VER} (3.10+ required)"
            break
        fi
    fi
done
if [[ -z "${PYTHON_CMD}" ]]; then
    fail "Python 3.10+ not found"
    MISSING+=("Python 3.10+ — https://www.python.org/downloads/ (macOS: brew install python@3.12)")
fi

# Check AI agents (kimi or pi)
HAS_KIMI=false
HAS_PI=false
if command -v kimi &>/dev/null; then
    HAS_KIMI=true
fi
if command -v pi &>/dev/null; then
    HAS_PI=true
fi

if [[ "${HAS_KIMI}" == "true" && "${HAS_PI}" == "true" ]]; then
    pass "AI agents: kimi + pi (both available)"
elif [[ "${HAS_KIMI}" == "true" ]]; then
    pass "AI agent: kimi (available)"
elif [[ "${HAS_PI}" == "true" ]]; then
    pass "AI agent: pi (available)"
else
    warn "AI agent: neither kimi nor pi found (at least one required)"
    WARNINGS+=("kimi or pi — install at least one AI agent CLI")
fi

# Check GitHub connectivity (optional, for clone + push)
# Prefer `gh api` so private repos with authenticated gh report OK.
if command -v gh &>/dev/null && gh api repos/samdharma/Ralph_loop --jq .name &>/dev/null; then
    pass "GitHub connectivity: OK (authenticated via gh)"
elif command -v git &>/dev/null && git ls-remote https://github.com/samdharma/Ralph_loop.git HEAD &>/dev/null 2>&1; then
    pass "GitHub connectivity: OK"
else
    warn "GitHub connectivity: cannot reach github.com (check network / gh auth)"
    WARNINGS+=("GitHub connectivity — required for clone and push")
fi

echo ""

# ──────────────────────────────────────────────────────────────
# If blockers exist, exit with install instructions
# ──────────────────────────────────────────────────────────────
if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo -e "${RED}Cannot install Ralph — missing prerequisites:${NC}"
    for m in "${MISSING[@]}"; do
        echo -e "  ${RED}✗${NC} ${m}"
    done
    echo ""
    echo "Install the above and re-run this installer."
    exit 1
fi

if [[ ${#WARNINGS[@]} -gt 0 ]]; then
    echo -e "${YELLOW}Warnings (Ralph will install, but some features need these):${NC}"
    for w in "${WARNINGS[@]}"; do
        echo -e "  ${YELLOW}⚠${NC}  ${w}"
    done
    echo ""
fi

# ──────────────────────────────────────────────────────────────
# Step 2: Install Ralph
# ──────────────────────────────────────────────────────────────
echo "Installing Ralph..."
echo ""

# If we're running from a cloned repo, use that as RALPH_HOME
if [[ -n "${REPO_DIR}" && -f "${REPO_DIR}/bin/ralph" ]]; then
    info "Installing from local clone: ${REPO_DIR}"
    RALPH_HOME="${REPO_DIR}"
else
    info "Installing to: ${RALPH_HOME}"
fi

# Ensure RALPH_HOME exists with the ralph source
if [[ ! -f "${RALPH_HOME}/bin/ralph" ]]; then
    info "Cloning Ralph repository..."
    # Try anonymous git clone first (works for public repos without gh auth).
    # Fall back to gh repo clone for private forks/repos where gh is authenticated.
    if git clone https://github.com/samdharma/Ralph_loop.git "${RALPH_HOME}" &>/dev/null; then
        : # success
    elif command -v gh &>/dev/null && gh repo clone samdharma/Ralph_loop "${RALPH_HOME}" &>/dev/null; then
        : # success via gh
    else
        echo -e "${RED}ERROR: Could not clone from GitHub.${NC}"
        echo "  Check your network connection and GitHub access."
        echo "  If you have a local copy, set RALPH_HOME:"
        echo "    export RALPH_HOME=/path/to/ralph"
        exit 1
    fi
    # Checkout the target branch (derive from current clone or default to ralph-v3.1)
    TARGET_BRANCH="ralph-v3.1"
    if [[ -n "${REPO_DIR}" ]]; then
        CURRENT_BRANCH=$(git -C "${REPO_DIR}" branch --show-current 2>/dev/null || true)
        if [[ -n "${CURRENT_BRANCH}" && "${CURRENT_BRANCH}" == ralph-v* ]]; then
            TARGET_BRANCH="${CURRENT_BRANCH}"
        fi
    fi
    git -C "${RALPH_HOME}" checkout "${TARGET_BRANCH}" 2>/dev/null || true
    pass "Cloned Ralph v3 to ${RALPH_HOME}"
fi

# Make everything executable
chmod +x "${RALPH_HOME}/bin/ralph" 2>/dev/null || true
chmod +x "${RALPH_HOME}/core/"*.py 2>/dev/null || true

# Install to PATH
INSTALL_PATH=""
if [[ -w "/usr/local/bin" ]]; then
    ln -sf "${RALPH_HOME}/bin/ralph" /usr/local/bin/ralph
    INSTALL_PATH="/usr/local/bin/ralph"
else
    mkdir -p "${HOME}/.local/bin"
    ln -sf "${RALPH_HOME}/bin/ralph" "${HOME}/.local/bin/ralph"
    INSTALL_PATH="${HOME}/.local/bin/ralph"
    warn "Add ~/.local/bin to your PATH:"
    echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# Add RALPH_HOME to shell profile if not already there
SHELL_PROFILE=""
if [[ -f "${HOME}/.zshrc" ]]; then
    SHELL_PROFILE="${HOME}/.zshrc"
elif [[ -f "${HOME}/.bashrc" ]]; then
    SHELL_PROFILE="${HOME}/.bashrc"
elif [[ -f "${HOME}/.bash_profile" ]]; then
    SHELL_PROFILE="${HOME}/.bash_profile"
fi

if [[ -n "${SHELL_PROFILE}" ]] && ! grep -q "RALPH_HOME" "${SHELL_PROFILE}" 2>/dev/null; then
    {
        echo ""
        echo "# Ralph v3 — Automated Build System"
        echo "export RALPH_HOME=\"${RALPH_HOME}\""
    } >> "${SHELL_PROFILE}"
    pass "Added RALPH_HOME to ${SHELL_PROFILE}"
fi

echo ""
echo -e "  ${GREEN}✓ Ralph v${RALPH_VERSION} installed → ${INSTALL_PATH}${NC}"
echo ""

# ──────────────────────────────────────────────────────────────
# Step 3: Post-install Verification
# ──────────────────────────────────────────────────────────────
echo "Verifying installation..."
echo ""

export RALPH_HOME
export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

if "${RALPH_HOME}/bin/ralph" version &>/dev/null; then
    pass "ralph CLI executable"
else
    fail "ralph CLI not executable — check permissions"
fi

if [[ -d "${RALPH_HOME}/core" ]]; then
    CORE_COUNT=$(ls -1 "${RALPH_HOME}/core/"*.py 2>/dev/null | wc -l | tr -d ' ')
    pass "Core modules: ${CORE_COUNT} files in ${RALPH_HOME}/core/"
else
    fail "Core directory missing: ${RALPH_HOME}/core/"
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Installation Complete!                 ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Quick start:"
echo "    source ~/.zshrc          # Reload shell (or ~/.bashrc)"
echo "    ralph version            # Verify: ralph v${RALPH_VERSION}"
echo "    ralph init my-project    # Create a new project"
echo "    cd my-project            # Enter the project"
echo "    ralph setup              # Verify prerequisites"
echo "    ralph daemon             # Start the build loop"
echo ""
echo "  Dependencies installed:"
echo "    git           $(git --version 2>/dev/null | head -1 || echo 'missing')"
echo "    gh            $(gh --version 2>/dev/null | head -1 || echo 'missing')"
echo "    python        $(python3 --version 2>/dev/null || echo 'missing')"
echo "    kimi          $(command -v kimi &>/dev/null && echo 'available' || echo 'not installed')"
echo "    pi            $(command -v pi &>/dev/null && echo 'available' || echo 'not installed')"
echo ""
