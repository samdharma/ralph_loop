#!/usr/bin/env bash
# Ralph Wiggum Loop Build System — One-Line Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/gastownhall/ralph/main/scripts/install.sh | bash
#
# Or from a local clone:
#   bash scripts/install.sh
#
# Installs ralph CLI to /usr/local/bin (or ~/.local/bin) and sets RALPH_HOME.

set -euo pipefail

RALPH_HOME="${RALPH_HOME:-$HOME/.ralph}"

# Determine the source directory (where this script lives)
if [[ -f "${BASH_SOURCE[0]}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
    REPO_DIR=""
fi

echo "╔══════════════════════════════════════════╗"
echo "║   Ralph Wiggum Loop Build System        ║"
echo "║   Installer v1.0.0                      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# If we're running from a cloned repo, use that as RALPH_HOME
if [[ -n "${REPO_DIR}" && -f "${REPO_DIR}/bin/ralph" ]]; then
    echo "→ Installing from local clone: ${REPO_DIR}"
    RALPH_HOME="${REPO_DIR}"
else
    echo "→ Installing to: ${RALPH_HOME}"
fi

# Ensure RALPH_HOME exists with the ralph source
if [[ ! -f "${RALPH_HOME}/bin/ralph" ]]; then
    echo "→ Cloning ralph repository..."
    if command -v git &>/dev/null; then
        git clone https://github.com/gastownhall/ralph.git "${RALPH_HOME}" 2>/dev/null || {
            echo "⚠  Could not clone from GitHub. If you have a local copy, set RALPH_HOME:"
            echo "   export RALPH_HOME=/path/to/ralph"
            exit 1
        }
    else
        echo "ERROR: git is required for installation."
        exit 1
    fi
fi

# Make everything executable
chmod +x "${RALPH_HOME}/bin/ralph" 2>/dev/null || true
chmod +x "${RALPH_HOME}/init.py" 2>/dev/null || true
chmod +x "${RALPH_HOME}/core/"*.sh 2>/dev/null || true

# Install to PATH
if [[ -w "/usr/local/bin" ]]; then
    ln -sf "${RALPH_HOME}/bin/ralph" /usr/local/bin/ralph
    INSTALL_PATH="/usr/local/bin/ralph"
else
    mkdir -p "${HOME}/.local/bin"
    ln -sf "${RALPH_HOME}/bin/ralph" "${HOME}/.local/bin/ralph"
    INSTALL_PATH="${HOME}/.local/bin/ralph"
    echo ""
    echo "  ⚠  Add ~/.local/bin to your PATH:"
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
    echo "" >> "${SHELL_PROFILE}"
    echo "# Ralph Wiggum Loop Build System" >> "${SHELL_PROFILE}"
    echo "export RALPH_HOME=\"${RALPH_HOME}\"" >> "${SHELL_PROFILE}"
    echo "  ✓ Added RALPH_HOME to ${SHELL_PROFILE}"
fi

echo ""
echo "  ✓ Ralph installed → ${INSTALL_PATH}"
echo ""
echo "  Quick start:"
echo "    ralph init     # Create a new project"
echo "    ralph status   # Show project health"
echo "    ralph help     # Show all commands"
echo ""
