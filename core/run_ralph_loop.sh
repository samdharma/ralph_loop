#!/usr/bin/env bash
# Ralph Wiggum Loop — Daemon Wrapper
# Ensures only one ralph_loop.sh instance runs at a time.
#
# Usage: ./scripts/ralph/run_ralph_loop.sh [args...]
# All arguments are forwarded to ralph_loop.sh.

set -euo pipefail

# Detect ralph core location
if [[ -n "${RALPH_CORE_DIR:-}" ]]; then
    CORE_DIR="${RALPH_CORE_DIR}"
elif [[ -d "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" ]]; then
    CORE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    CORE_DIR=""
fi

PROJECT_DIR="${RALPH_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${PROJECT_DIR}"

PIDFILE="${PROJECT_DIR}/.ralph_loop.pid"
LOGFILE="${PROJECT_DIR}/logs/ralph_loop.log"

mkdir -p "${PROJECT_DIR}/logs"

# Check if already running
if [[ -f "${PIDFILE}" ]]; then
    PID=$(cat "${PIDFILE}" 2>/dev/null || echo "")
    if [[ -n "${PID}" ]] && ps -p "${PID}" > /dev/null 2>&1; then
        echo "[run_ralph_loop] Ralph loop already running (PID ${PID})"
        exit 0
    else
        echo "[run_ralph_loop] Stale PID file found, removing..."
        rm -f "${PIDFILE}"
    fi
fi

# Determine ralph_loop.sh location
RALPH_LOOP_SCRIPT="${RALPH_LOOP_SCRIPT:-${CORE_DIR}/ralph_loop.sh}"

# Start ralph_loop.sh in background
echo "[run_ralph_loop] Starting ralph_loop.sh..."
nohup bash "${RALPH_LOOP_SCRIPT}" "$@" >> "${LOGFILE}" 2>&1 &
NEW_PID=$!
echo "${NEW_PID}" > "${PIDFILE}"
echo "[run_ralph_loop] Ralph loop started with PID ${NEW_PID}"
echo "[run_ralph_loop] Logs: ${LOGFILE}"
