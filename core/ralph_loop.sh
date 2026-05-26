#!/usr/bin/env bash
# Ralph Wiggum Loop Harness v1 — Core Engine
# Generic agentic development loop for any project using beads issue tracking.
#
# Usage: ./scripts/ralph/ralph_loop.sh [--force] [--tier=full] [--tag=<tag>] [--agent=kimi|pi] [--ticket=<id>]
# Requires: Kimi CLI (kimi) or Pi Coding Agent (pi), and beads (bd) installed.
#
# Environment variables:
#   RALPH_PROJECT_DIR   - Path to project root (default: parent of scripts/ralph/)
#   RALPH_CORE_DIR      - Path to ralph core scripts (default: auto-detected)
#   RALPH_PROMPT_BASE   - Path to base agent prompt (default: docs/agent/PROMPT.md)
#   RALPH_PROMPT_DIR    - Path to type-specific prompt extensions (default: docs/agent/prompts)
#   RALPH_PROGRESS_FILE - Path to progress log (default: docs/agent/PROGRESS.md)
#   RALPH_CHECKPOINT    - Path to checkpoint file (default: .ralph_checkpoint.json)
#   RALPH_LOG_DIR       - Directory for logs (default: logs)
#   RALPH_ALLOW_E2E     - Set to 1 to allow e2e/performance tiers (default: 0)
#   RALPH_METRICS_FILE  - Override metrics jsonl path
#   RALPH_PREFLIGHT_SCRIPT - Override preflight script path
#   RALPH_VALIDATE_SCRIPT  - Override validate script path
#   RALPH_METRICS_SCRIPT   - Override metrics script path

set -euo pipefail

# Detect ralph core location
if [[ -n "${RALPH_CORE_DIR:-}" ]]; then
    CORE_DIR="${RALPH_CORE_DIR}"
elif [[ -d "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" ]]; then
    CORE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    echo "[RALPH] ERROR: Cannot determine RALPH_CORE_DIR. Set it explicitly."
    exit 1
fi

# Detect project directory
PROJECT_DIR="${RALPH_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${PROJECT_DIR}"

# --- Configuration ---
FORCE=0
TEST_TIER="targeted"
BEADS_TAG=""
AGENT=""
TICKET_ID=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE=1
            shift
            ;;
        --tier)
            TEST_TIER="$2"
            shift 2
            ;;
        --tier=*)
            TEST_TIER="${1#*=}"
            shift
            ;;
        --tag)
            BEADS_TAG="$2"
            shift 2
            ;;
        --tag=*)
            BEADS_TAG="${1#*=}"
            shift
            ;;
        --agent)
            AGENT="$2"
            shift 2
            ;;
        --agent=*)
            AGENT="${1#*=}"
            shift
            ;;
        --ticket)
            TICKET_ID="$2"
            shift 2
            ;;
        --ticket=*)
            TICKET_ID="${1#*=}"
            shift
            ;;
        *)
            echo "[RALPH] Unknown argument: $1"
            exit 1
            ;;
    esac
done

PROMPT_BASE="${RALPH_PROMPT_BASE:-${PROJECT_DIR}/docs/agent/PROMPT.md}"
PROMPT_DIR="${RALPH_PROMPT_DIR:-${PROJECT_DIR}/docs/agent/prompts}"
PROGRESS_FILE="${RALPH_PROGRESS_FILE:-${PROJECT_DIR}/docs/agent/PROGRESS.md}"
CHECKPOINT_FILE="${RALPH_CHECKPOINT:-${PROJECT_DIR}/.ralph_checkpoint.json}"
PREFLIGHT_SCRIPT="${RALPH_PREFLIGHT_SCRIPT:-${CORE_DIR}/ralph_preflight.sh}"
VALIDATE_SCRIPT="${RALPH_VALIDATE_SCRIPT:-${CORE_DIR}/ralph_validate.sh}"
METRICS_SCRIPT="${RALPH_METRICS_SCRIPT:-${CORE_DIR}/ralph_metrics.sh}"
LOG_DIR="${RALPH_LOG_DIR:-${PROJECT_DIR}/logs}"
mkdir -p "${LOG_DIR}"

# --- Safety Checks ---

if [[ ! -f "${PROMPT_BASE}" ]]; then
    echo "[RALPH] ERROR: ${PROMPT_BASE} not found."
    echo "[RALPH] Hint: Did you run 'ralph init'? This file is generated during project init."
    echo "[RALPH] Or set RALPH_PROMPT_BASE to point to your custom prompt file."
    exit 1
fi

# Detect available agent
AGENT_CMD=""
if [[ -n "${AGENT}" ]]; then
    if ! command -v "${AGENT}" &>/dev/null; then
        echo "[RALPH] ERROR: Requested agent '${AGENT}' not found in PATH."
        exit 1
    fi
    if [[ "${AGENT}" != "kimi" && "${AGENT}" != "pi" ]]; then
        echo "[RALPH] ERROR: Unsupported agent '${AGENT}'. Use 'kimi' or 'pi'."
        exit 1
    fi
    AGENT_CMD="${AGENT}"
elif command -v kimi &>/dev/null; then
    AGENT_CMD="kimi"
elif command -v pi &>/dev/null; then
    AGENT_CMD="pi"
else
    echo "[RALPH] ERROR: No supported agent found in PATH (kimi or pi)."
    exit 1
fi

# Check beads is available
if ! command -v bd &>/dev/null; then
    echo "[RALPH] ERROR: beads (bd) not found in PATH."
    echo "[RALPH] Install via: https://github.com/beadsboard/beads"
    exit 1
fi

# --- Signal trapping for graceful shutdown ---
_cleanup_on_signal() {
    echo ""
    echo "[RALPH] Caught shutdown signal. Clearing checkpoint..."
    rm -f "${CHECKPOINT_FILE}"
    exit 130
}
trap _cleanup_on_signal SIGINT SIGTERM

# --- Checkpoint Resume (before dirty-worktree check) ---
if [[ -f "${CHECKPOINT_FILE}" ]]; then
    echo "[RALPH] WARNING: Checkpoint file found from previous run."
    PRE_COMMIT=$(python3 -c "import json; d=json.load(open('${CHECKPOINT_FILE}')); print(d.get('pre_commit',''))" 2>/dev/null || true)
    if [[ -n "${PRE_COMMIT}" ]]; then
        NEW_COMMITS=$(git rev-list --count "${PRE_COMMIT}..HEAD" 2>/dev/null || echo "0")
        if [[ "${NEW_COMMITS}" -gt 0 ]]; then
            echo "[RALPH] Agent made ${NEW_COMMITS} commit(s) since ${PRE_COMMIT}. Preserving commits; only resetting uncommitted changes."
            git checkout -- . 2>/dev/null || true
            git clean -fd 2>/dev/null || true
        elif [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
            echo "[RALPH] Dirty worktree detected. Rolling back to pre-iteration commit ${PRE_COMMIT}..."
            git reset --hard "${PRE_COMMIT}" || true
        fi
    fi
    TASK_ID=$(python3 -c "import json; d=json.load(open('${CHECKPOINT_FILE}')); print(d.get('task_id',''))" 2>/dev/null || true)
    ITER_CHECKPOINT=$(python3 -c "import json; d=json.load(open('${CHECKPOINT_FILE}')); print(d.get('iteration',''))" 2>/dev/null || true)
    if [[ -n "${TASK_ID}" ]]; then
        echo "[RALPH] Marking previous task ${TASK_ID} as failed due to incomplete iteration."
        bd update "${TASK_ID}" --status open --notes="Iteration ${ITER_CHECKPOINT} failed / interrupted. Rolled back." 2>/dev/null || true
        bash "${METRICS_SCRIPT}" task_rolled_back task_id="${TASK_ID}" iteration="${ITER_CHECKPOINT}" reason="checkpoint_recovery"
    fi
    rm -f "${CHECKPOINT_FILE}"
fi

# Check for uncommitted changes (AFTER checkpoint recovery)
if [[ ${FORCE} -eq 0 ]]; then
    if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
        echo "[RALPH] ERROR: Working tree has uncommitted changes."
        echo "        Commit or stash them before running the loop, or use --force."
        exit 1
    fi
else
    echo "[RALPH] WARNING: --force passed; skipping dirty-worktree check."
fi

echo "[RALPH] Agent detected: ${AGENT_CMD}"
echo "[RALPH] Beads detected: $(bd --version 2>/dev/null || echo 'unknown')"
echo "[RALPH] Project: ${PROJECT_DIR}"
echo "[RALPH] Prompt base: ${PROMPT_BASE}"

SINGLE_SHOT=0
if [[ -n "${TICKET_ID}" ]]; then
    echo "[RALPH] Single-shot mode for ticket: ${TICKET_ID}"

    TICKET_RAW=$(bd show "${TICKET_ID}" --json 2>/dev/null || true)
    TICKET_JSON=$(echo "${TICKET_RAW}" | python3 -c "import sys,json; lines=[l for l in sys.stdin.read().splitlines() if l.strip()]; print(json.dumps([json.loads(l) for l in lines if l.strip()]))" 2>/dev/null || echo "[]")
    TICKET_COUNT=$(echo "${TICKET_JSON}" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [[ "${TICKET_COUNT}" -eq 0 ]]; then
        echo "[RALPH] ERROR: Ticket ${TICKET_ID} not found."
        exit 1
    fi

    TICKET_STATUS=$(echo "${TICKET_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0].get('status',''))" 2>/dev/null || true)
    if [[ "${TICKET_STATUS}" != "open" ]]; then
        echo "[RALPH] ERROR: Ticket ${TICKET_ID} is not ready (status: ${TICKET_STATUS})."
        echo "[RALPH] Only 'open' tickets with no blockers can be built."
        exit 1
    fi

    IS_READY=$(bd ready --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for x in d if x.get('id')=='${TICKET_ID}'))" 2>/dev/null || echo "0")
    if [[ "${IS_READY}" -eq 0 ]]; then
        DEP_COUNT=$(bd dep list "${TICKET_ID}" --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        if [[ "${DEP_COUNT}" -gt 0 ]]; then
            echo "[RALPH] ERROR: Ticket ${TICKET_ID} has unresolved dependencies."
            echo ""
            bd dep tree "${TICKET_ID}"
            echo ""
            echo "[RALPH] Resolve dependencies before building this ticket."
            exit 1
        else
            echo "[RALPH] ERROR: Ticket ${TICKET_ID} is not in ready state (may be blocked by external factors)."
            exit 1
        fi
    fi

    READY_JSON="${TICKET_JSON}"
    SINGLE_SHOT=1
    echo "[RALPH] Ticket validated: ready with no blockers."
fi

echo "[RALPH] Starting loop..."
echo "================================================"

ITERATION=0
while true; do
    ITERATION=$((ITERATION + 1))

    # --- Get ready tasks from beads ---
    if [[ ${SINGLE_SHOT} -eq 0 ]]; then
        if [[ -n "${BEADS_TAG}" ]]; then
            READY_JSON=$(bd ready --label "${BEADS_TAG}" --json 2>/dev/null || echo "[]")
            echo "[RALPH] Filtered by tag: ${BEADS_TAG}"
        else
            READY_JSON=$(bd ready --json 2>/dev/null || echo "[]")
        fi
    else
        echo "[RALPH] Single-shot mode: using ticket ${TICKET_ID}"
    fi

    # --- Filter and sort ready tasks deterministically ---
    # Rules: skip epic/feature containers; sort by feature number ascending,
    # then task number ascending. This ensures Feature 1 is built before
    # Feature 2, and task 1 before task 2 within a feature.
    if [[ ${SINGLE_SHOT} -eq 0 ]]; then
        READY_JSON=$(echo "${READY_JSON}" | python3 -c "
import sys, json
tasks = json.load(sys.stdin)
# skip epics and features
tasks = [t for t in tasks if t.get('issue_type') not in ('epic', 'feature')]
# sort by feature number then task number from dotted id like 'PROJECT.1.2'
def sort_key(t):
    tid = t.get('id', '')
    parts = tid.split('.')
    feat = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    task = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return (feat, task)
tasks.sort(key=sort_key)
print(json.dumps(tasks))
")
        echo "[RALPH] Deterministic sort: feature ascending, task ascending"
    fi
    READY_COUNT=$(echo "${READY_JSON}" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

    if [[ "${READY_COUNT}" -eq 0 ]]; then
        echo ""
        echo "[RALPH] No ready tasks remaining in beads."
        echo "[RALPH] Loop complete. Total iterations: ${ITERATION}"
        rm -f "${CHECKPOINT_FILE}"
        exit 0
    fi

    # --- Pre-flight Guardrails: iterate through ready tasks ---
    TASK_ID=""
    TASK_TITLE=""
    TASK_TYPE=""
    TASK_LABELS=""

    for i in $(python3 -c "import sys,json; print(' '.join(str(i) for i in range(len(json.load(sys.stdin)))))" <<< "${READY_JSON}"); do
        CAND_ID=$(echo "${READY_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)[${i}].get('id',''))")
        CAND_TITLE=$(echo "${READY_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)[${i}].get('title',''))")
        CAND_TYPE=$(echo "${READY_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)[${i}].get('type','task'))")
        CAND_LABELS=$(echo "${READY_JSON}" | python3 -c "import sys,json; print(','.join(json.load(sys.stdin)[${i}].get('labels',[])))")

        PREFLIGHT_RESULT=$(bash "${PREFLIGHT_SCRIPT}" "${CAND_LABELS}" "${CAND_TYPE}" 2>/dev/null || echo "BLOCKED: preflight_script_failed")
        if [[ "${PREFLIGHT_RESULT}" == "READY" ]]; then
            TASK_ID="${CAND_ID}"
            TASK_TITLE="${CAND_TITLE}"
            TASK_TYPE="${CAND_TYPE}"
            TASK_LABELS="${CAND_LABELS}"
            break
        else
            echo "[RALPH] Task ${CAND_ID} skipped — ${PREFLIGHT_RESULT}"
        fi
    done

    if [[ -z "${TASK_ID}" ]]; then
        if [[ ${SINGLE_SHOT} -eq 1 ]]; then
            echo "[RALPH] ERROR: Single-shot ticket ${TICKET_ID} failed pre-flight checks."
            exit 1
        fi
        echo ""
        echo "[RALPH] Iteration ${ITERATION} | All ${READY_COUNT} ready tasks failed pre-flight checks."
        bash "${METRICS_SCRIPT}" all_tasks_blocked ready_count="${READY_COUNT}" iteration="${ITERATION}"
        echo "[RALPH] Sleeping 60 seconds before next check..."
        sleep 60
        continue
    fi

    # --- Claim task ---
    bd update "${TASK_ID}" --claim 2>/dev/null || true
    bd update "${TASK_ID}" --status in_progress 2>/dev/null || true

    echo ""
    echo "[RALPH] Iteration ${ITERATION} | Task: ${TASK_ID}"
    echo "[RALPH] Title: ${TASK_TITLE}"
    echo "[RALPH] Type: ${TASK_TYPE} | Labels: ${TASK_LABELS}"
    echo "[RALPH] Ready tasks remaining: ${READY_COUNT}"
    echo "[RALPH] Invoking agent with adaptive prompt ..."
    echo "------------------------------------------------"

    # --- Write checkpoint ---
    PRE_COMMIT_HASH=$(git rev-parse HEAD)
    python3 -c "
import json
json.dump({'iteration':${ITERATION},'task_id':'${TASK_ID}','pre_commit':'${PRE_COMMIT_HASH}','tier':'${TEST_TIER}'}, open('${CHECKPOINT_FILE}','w'))
"

    # --- Adaptive Prompt Assembly ---
    TASK_DESC=$(bd show "${TASK_ID}" --json 2>/dev/null | python3 -c "import sys,json; d=json.loads(sys.stdin.read().splitlines()[0]) if sys.stdin.read().strip() else {}; print(d.get('description',''))" 2>/dev/null || echo "")

    # Start with base prompt
    FULL_PROMPT="$(cat "${PROMPT_BASE}")"

    # Append type-specific guidance if available
    TYPE_PROMPT_FILE="${PROMPT_DIR}/${TASK_TYPE}.md"
    if [[ -f "${TYPE_PROMPT_FILE}" ]]; then
        FULL_PROMPT="${FULL_PROMPT}

$(cat "${TYPE_PROMPT_FILE}")"
    fi

    # --- Detect phase-specific build reference doc ---
    PHASE_LABEL=$(echo "${TASK_LABELS}" | grep -oE 'phase-[0-9]+[a-z]*' | head -1)
    BUILD_PHASE_DOC=""
    if [[ -n "${PHASE_LABEL}" ]]; then
        PHASE_NUM=$(echo "${PHASE_LABEL}" | sed 's/phase-//')
        CANDIDATE="${PROJECT_DIR}/docs/reference/BUILD_PHASE_${PHASE_NUM}.md"
        if [[ -f "${CANDIDATE}" ]]; then
            BUILD_PHASE_DOC="docs/reference/BUILD_PHASE_${PHASE_NUM}.md"
        fi
    fi

    # Append task context
    FULL_PROMPT="${FULL_PROMPT}

---

## Current Task

- **ID**: ${TASK_ID}
- **Title**: ${TASK_TITLE}
- **Type**: ${TASK_TYPE}
- **Labels**: ${TASK_LABELS}
- **Description**: ${TASK_DESC}
- **Test Tier**: ${TEST_TIER}
"

    if [[ -n "${BUILD_PHASE_DOC}" ]]; then
        FULL_PROMPT="${FULL_PROMPT}
- **Build Reference**: ${BUILD_PHASE_DOC}

> **MANDATORY: Read \`${BUILD_PHASE_DOC}\` BEFORE researching APIs or libraries.**
> This doc contains pre-discovered type mappings, SDK field references, and implementation patterns.
> It saves ~20-30 steps of redundant research per iteration.
"
    fi

    FULL_PROMPT="${FULL_PROMPT}

Run \`bash scripts/ralph/ralph_validate.sh --tier=${TEST_TIER}\` for validation.
"

    # Log metrics
    bash "${METRICS_SCRIPT}" iteration_start task_id="${TASK_ID}" iteration="${ITERATION}" task_type="${TASK_TYPE}" tier="${TEST_TIER}"

    if [[ "${AGENT_CMD}" == "kimi" ]]; then
        # Non-interactive print mode
        kimi --print -p "${FULL_PROMPT}"
    else
        # Non-interactive print mode
        pi --print "${FULL_PROMPT}"
    fi

    echo ""
    echo "[RALPH] Agent iteration ${ITERATION} finished."

    # --- Post-iteration: clear checkpoint if clean, log metrics ---
    if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
        rm -f "${CHECKPOINT_FILE}"
        bash "${METRICS_SCRIPT}" checkpoint_cleared task_id="${TASK_ID}" iteration="${ITERATION}" reason="clean_worktree"
    else
        bash "${METRICS_SCRIPT}" checkpoint_retained task_id="${TASK_ID}" iteration="${ITERATION}" reason="dirty_worktree"
    fi

    # Log end-of-iteration metrics
    bash "${METRICS_SCRIPT}" iteration_end task_id="${TASK_ID}" iteration="${ITERATION}"

    if [[ ${SINGLE_SHOT} -eq 1 ]]; then
        echo ""
        echo "[RALPH] Single-shot complete. Exiting."
        rm -f "${CHECKPOINT_FILE}"
        exit 0
    fi

    echo "[RALPH] Sleeping 5 seconds before next loop..."
    sleep 5
done
