#!/usr/bin/env bash
# Ralph Wiggum Daily/Weekly Report v1
# Generates operational summary reports from project data.
#
# Usage:
#   bash scripts/ralph/ralph_report.sh --daily [YYYY-MM-DD]
#   bash scripts/ralph/ralph_report.sh --weekly [weeks_back]
#   bash scripts/ralph/ralph_report.sh --output text|html [--save]
#
# Environment variables:
#   RALPH_PROJECT_DIR  - Path to project root
#   RALPH_PYTHON_CMD   - Python executable to use
#   RALPH_VENV_PATH    - Path to virtual env (default: .venv)

set -euo pipefail

PROJECT_DIR="${RALPH_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${PROJECT_DIR}"

VENV_PATH="${RALPH_VENV_PATH:-${PROJECT_DIR}/.venv}"
PYTHON_CMD="${RALPH_PYTHON_CMD:-}"

if [[ -z "${PYTHON_CMD}" ]]; then
    if [[ -f "${VENV_PATH}/bin/python" ]]; then
        PYTHON_CMD="${VENV_PATH}/bin/python"
    elif [[ -f "${VENV_PATH}/bin/python3" ]]; then
        PYTHON_CMD="${VENV_PATH}/bin/python3"
    elif command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
    else
        echo "[RALPH REPORT] ERROR: No Python executable found."
        exit 1
    fi
fi

if [[ -z "${VIRTUAL_ENV:-}" && -f "${VENV_PATH}/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${VENV_PATH}/bin/activate"
fi

# Find ralph_report.py (could be in core/ or scripts/ralph/)
REPORT_PY=""
if [[ -f "${PROJECT_DIR}/scripts/ralph/ralph_report.py" ]]; then
    REPORT_PY="${PROJECT_DIR}/scripts/ralph/ralph_report.py"
elif [[ -f "${CORE_DIR:-/dev/null}/ralph_report.py" ]]; then
    REPORT_PY="${CORE_DIR}/ralph_report.py"
else
    echo "[RALPH REPORT] ERROR: ralph_report.py not found."
    exit 1
fi

# Forward all arguments to the Python implementation
exec "${PYTHON_CMD}" "${REPORT_PY}" "$@"
