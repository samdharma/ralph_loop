#!/usr/bin/env bash
# Ralph Wiggum Build Orchestrator v1 — Single-Ticket 4-Stage Pipeline
#
# Usage:
#   ralph build --ticket=<id> [--agent=kimi|pi] [--tier=targeted] [--force]
#               [--auto-close] [--max-retries=2] [--no-commit]
#
# Runs design → test → implement → verify for a single ticket, with
# checkpoint/resume support and automatic state management.

set -euo pipefail

# ──────────────────────────────────────────────────────────────
# Detect paths
# ──────────────────────────────────────────────────────────────
if [[ -n "${RALPH_CORE_DIR:-}" ]]; then
    CORE_DIR="${RALPH_CORE_DIR}"
elif [[ -d "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" ]]; then
    CORE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    echo "[RALPH BUILD] ERROR: Cannot determine RALPH_CORE_DIR." >&2
    exit 1
fi

PROJECT_DIR="${RALPH_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${PROJECT_DIR}"

# ──────────────────────────────────────────────────────────────
# Configuration & defaults
# ──────────────────────────────────────────────────────────────
TICKET_ID=""
AGENT=""
TEST_TIER="targeted"
FORCE=0
AUTO_CLOSE=0
MAX_RETRIES=2
AUTO_COMMIT=1

LOG_DIR="${RALPH_LOG_DIR:-${PROJECT_DIR}/logs}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/ralph_build.log"

RALPH_DIR="${PROJECT_DIR}/.ralph"
mkdir -p "${RALPH_DIR}"
STATE_FILE="${RALPH_DIR}/build_state.json"

METRICS_SCRIPT="${RALPH_METRICS_SCRIPT:-${CORE_DIR}/ralph_metrics.sh}"

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
log() {
    local msg="[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $1"
    echo "${msg}" | tee -a "${LOG_FILE}"
}

log_raw() {
    echo "$1" | tee -a "${LOG_FILE}"
}

fail() {
    log "ERROR: $1"
    exit 1
}

usage() {
    cat <<EOF
Usage: ralph build --ticket=<id> [options]

Options:
  --ticket=<id>        Ticket to build (required)
  --agent=kimi|pi      Agent to use (auto-detected if omitted)
  --tier=<tier>        Validation tier: smoke|targeted|integration|full (default: targeted)
  --force              Skip dirty-worktree guardrails
  --auto-close         Close ticket automatically after validation pass
  --max-retries=<n>    Retry failed stages (default: 2)
  --no-commit          Do NOT auto-commit each stage (not recommended; breaks resume)
  --help               Show this help
EOF
}

# ──────────────────────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ticket)
            TICKET_ID="$2"
            shift 2
            ;;
        --ticket=*)
            TICKET_ID="${1#*=}"
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
        --tier)
            TEST_TIER="$2"
            shift 2
            ;;
        --tier=*)
            TEST_TIER="${1#*=}"
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --auto-close)
            AUTO_CLOSE=1
            shift
            ;;
        --max-retries)
            MAX_RETRIES="$2"
            shift 2
            ;;
        --max-retries=*)
            MAX_RETRIES="${1#*=}"
            shift
            ;;
        --no-commit)
            AUTO_COMMIT=0
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "Unknown argument: $1"
            ;;
    esac
done

if [[ -z "${TICKET_ID}" ]]; then
    usage
    fail "--ticket=<id> is required."
fi

if [[ "${MAX_RETRIES}" =~ ^[0-9]+$ ]]; then
    : # ok
else
    fail "--max-retries must be a non-negative integer."
fi

# ──────────────────────────────────────────────────────────────
# Preconditions
# ──────────────────────────────────────────────────────────────
if ! command -v bd &>/dev/null; then
    fail "beads (bd) not found in PATH."
fi

if ! command -v git &>/dev/null; then
    fail "git not found in PATH."
fi

if [[ ! -d "${PROJECT_DIR}/.beads" ]]; then
    fail "beads not initialized. Run 'ralph setup' first."
fi

# ──────────────────────────────────────────────────────────────
# State management
# ──────────────────────────────────────────────────────────────
init_state() {
    python3 -c "
import json, datetime
state = {
    'ticket_id': '${TICKET_ID}',
    'agent': '${AGENT}',
    'tier': '${TEST_TIER}',
    'started_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'status': 'in_progress',
    'stages': {},
    'validation': {'status': 'pending', 'output': ''},
    'final_status': ''
}
for s in ['design','test','implement','verify']:
    state['stages'][s] = {'status': 'pending', 'completed_at': None, 'retries': 0, 'output': ''}
print(json.dumps(state, indent=2))
" > "${STATE_FILE}"
}

load_state() {
    python3 -c "import json; print(json.dumps(json.load(open('${STATE_FILE}'))))" 2>/dev/null || echo "{}"
}

update_stage() {
    local stage="$1"
    local status="$2"
    local output="${3:-}"
    python3 - "${STATE_FILE}" "${stage}" "${status}" "${output}" <<'PY'
import json, datetime, sys
state_file, stage, status, output = sys.argv[1:5]
with open(state_file) as f:
    state = json.load(f)
state['stages'][stage]['status'] = status
state['stages'][stage]['completed_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
state['stages'][stage]['output'] = output
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
PY
}

update_validation() {
    local status="$1"
    local output="${2:-}"
    python3 - "${STATE_FILE}" "${status}" "${output}" <<'PY'
import json, datetime, sys
state_file, status, output = sys.argv[1:4]
with open(state_file) as f:
    state = json.load(f)
state['validation']['status'] = status
state['validation']['output'] = output
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
PY
}

update_final_status() {
    local status="$1"
    python3 - <<PY
import json, datetime
with open('${STATE_FILE}') as f:
    state = json.load(f)
state['status'] = '${status}'
state['final_status'] = '${status}'
state['completed_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
with open('${STATE_FILE}', 'w') as f:
    json.dump(state, f, indent=2)
PY
}

# ──────────────────────────────────────────────────────────────
# Ticket validation
# ──────────────────────────────────────────────────────────────
validate_ticket() {
    log "Validating ticket: ${TICKET_ID}"

    local ticket_raw
    ticket_raw=$(bd show "${TICKET_ID}" --json 2>/dev/null || true)
    local ticket_count
    ticket_count=$(echo "${ticket_raw}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d if isinstance(d,list) else [d]))" 2>/dev/null || echo "0")

    if [[ "${ticket_count}" -eq 0 ]]; then
        fail "Ticket ${TICKET_ID} not found."
    fi

    local ticket_status
    ticket_status=$(echo "${ticket_raw}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0].get('status','') if isinstance(d,list) else d.get('status',''))" 2>/dev/null || true)
    if [[ "${ticket_status}" != "open" ]]; then
        fail "Ticket ${TICKET_ID} is not open (status: ${ticket_status})."
    fi

    local is_ready
    is_ready=$(bd ready --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for x in d if x.get('id')=='${TICKET_ID}'))" 2>/dev/null || echo "0")
    if [[ "${is_ready}" -eq 0 ]]; then
        fail "Ticket ${TICKET_ID} is not in ready state (dependencies or blockers)."
    fi

    log "Ticket validated: ${TICKET_ID} is open and ready."
}

# ──────────────────────────────────────────────────────────────
# Stage execution
# ──────────────────────────────────────────────────────────────
run_stage() {
    local stage="$1"
    local attempt=0
    local extra_args=()

    if [[ ${FORCE} -eq 1 ]]; then
        extra_args+=("--force")
    fi
    if [[ -n "${AGENT}" ]]; then
        extra_args+=("--agent=${AGENT}")
    fi
    # After the first stage, the ticket is in_progress. Subsequent stages
    # must skip the "open" status check so the pipeline can continue.
    if [[ "${stage}" != "design" ]]; then
        extra_args+=("--skip-status-check")
    fi

    while [[ ${attempt} -le ${MAX_RETRIES} ]]; do
        log "------------------------------------------------"
        log "Stage: ${stage} | Attempt: $((attempt + 1))/$((MAX_RETRIES + 1))"
        log "------------------------------------------------"

        update_stage "${stage}" "running" ""

        # Clear any stale checkpoint from a prior failed run so ralph_loop.sh
        # does not roll back work from a previous stage.
        rm -f "${PROJECT_DIR}/.ralph_checkpoint.json"

        local safe_ticket
        safe_ticket="${TICKET_ID//\//_}" # sanitize ticket id for filename
        local stage_log
        stage_log="${LOG_DIR}/ralph_build_${safe_ticket}_${stage}_attempt_$((attempt + 1)).log"

        local exit_code=0
        bash "${CORE_DIR}/ralph_loop.sh" --session="${stage}" --ticket="${TICKET_ID}" "${extra_args[@]}" > "${stage_log}" 2>&1 || exit_code=$?

        if [[ ${exit_code} -eq 0 ]]; then
            log "Stage ${stage} completed successfully."
            update_stage "${stage}" "done" "See ${stage_log}"
            commit_stage "${stage}"
            return 0
        fi

        attempt=$((attempt + 1))
        log "Stage ${stage} failed (exit ${exit_code})."
        if [[ ${attempt} -le ${MAX_RETRIES} ]]; then
            log "Retrying in 5 seconds..."
            sleep 5
        fi
    done

    local safe_ticket="${TICKET_ID//\//_}"
    update_stage "${stage}" "failed" "See ${LOG_DIR}/ralph_build_${safe_ticket}_${stage}_attempt_*.log"
    return 1
}

# ──────────────────────────────────────────────────────────────
# Auto-commit each stage so the next stage starts from a clean
# worktree and checkpoint recovery does not roll back progress.
# ──────────────────────────────────────────────────────────────
commit_stage() {
    local stage="$1"

    if [[ ${AUTO_COMMIT} -eq 0 ]]; then
        log "Auto-commit disabled; skipping commit for ${stage}."
        return 0
    fi

    if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
        log "No changes to commit for ${stage}."
        return 0
    fi

    git add -A
    git commit -m "[ralph] ${stage}: ${TICKET_ID}" --quiet || {
        log "WARNING: Commit failed for ${stage}; proceeding anyway."
        return 0
    }
    log "Committed ${stage} changes."
}

# ──────────────────────────────────────────────────────────────
# Validation gate
# ──────────────────────────────────────────────────────────────
run_validation() {
    log "Running validation gate: ralph validate --tier=${TEST_TIER}"

    local val_log
    val_log="${LOG_DIR}/ralph_build_${TICKET_ID//\//_}_validation.log"

    local exit_code=0
    bash "${CORE_DIR}/ralph_validate.sh" --tier="${TEST_TIER}" > "${val_log}" 2>&1 || exit_code=$?

    if [[ ${exit_code} -eq 0 ]]; then
        log "Validation passed."
        update_validation "passed" "See ${val_log}"
        return 0
    else
        log "Validation failed."
        update_validation "failed" "See ${val_log}"
        return 1
    fi
}

# ──────────────────────────────────────────────────────────────
# Ticket status updates
# ──────────────────────────────────────────────────────────────
mark_review() {
    log "Marking ticket ${TICKET_ID} for human review."
    bd update "${TICKET_ID}" --status review --notes="Ralph 4-stage pipeline complete. Awaiting human verification." 2>/dev/null || true
}

mark_done() {
    log "Closing ticket ${TICKET_ID}."
    bd update "${TICKET_ID}" --status done --notes="Completed by Ralph build orchestrator." 2>/dev/null || true
}

mark_failed() {
    local stage="$1"
    log "Marking ticket ${TICKET_ID} as failed at stage ${stage}."
    bd update "${TICKET_ID}" --status open --notes="Ralph build failed at ${stage} stage. Manual intervention required." 2>/dev/null || true
}

# ──────────────────────────────────────────────────────────────
# Main orchestration
# ──────────────────────────────────────────────────────────────
main() {
    log "================================================"
    log "Ralph Build Orchestrator started"
    log "Ticket: ${TICKET_ID}"
    log "Agent: ${AGENT:-auto-detected}"
    log "Tier: ${TEST_TIER}"
    log "Auto-commit: $([[ ${AUTO_COMMIT} -eq 1 ]] && echo yes || echo no)"
    log "Auto-close: $([[ ${AUTO_CLOSE} -eq 1 ]] && echo yes || echo no)"
    log "================================================"

    validate_ticket

    # Initialize or resume state
    if [[ -f "${STATE_FILE}" ]]; then
        local existing_ticket
        existing_ticket=$(python3 -c "import json; print(json.load(open('${STATE_FILE}')).get('ticket_id',''))" 2>/dev/null || true)
        if [[ "${existing_ticket}" == "${TICKET_ID}" ]]; then
            log "Resuming existing build state."
        else
            log "Existing state is for a different ticket (${existing_ticket}); starting fresh."
            init_state
        fi
    else
        init_state
    fi

    # Ensure clean worktree at start unless --force
    if [[ ${FORCE} -eq 0 && -n "$(git status --porcelain 2>/dev/null)" ]]; then
        fail "Working tree has uncommitted changes. Commit or stash them, or use --force."
    fi

    # Record start metric
    bash "${METRICS_SCRIPT}" build_started ticket_id="${TICKET_ID}" agent="${AGENT:-auto}" tier="${TEST_TIER}" 2>/dev/null || true

    local stages=("design" "test" "implement" "verify")

    for stage in "${stages[@]}"; do
        local stage_status
        stage_status=$(python3 -c "import json; print(json.load(open('${STATE_FILE}')).get('stages',{}).get('${stage}',{}).get('status','pending'))" 2>/dev/null || echo "pending")

        if [[ "${stage_status}" == "done" ]]; then
            log "Stage ${stage} already completed; skipping."
            continue
        fi

        if ! run_stage "${stage}"; then
            mark_failed "${stage}"
            update_final_status "failed"
            bash "${METRICS_SCRIPT}" build_failed ticket_id="${TICKET_ID}" stage="${stage}" 2>/dev/null || true
            fail "Build stopped at ${stage} stage."
        fi
    done

    # Run objective validation gate
    if ! run_validation; then
        mark_failed "validation"
        update_final_status "failed"
        bash "${METRICS_SCRIPT}" build_failed ticket_id="${TICKET_ID}" stage="validation" 2>/dev/null || true
        fail "Validation failed. Ticket left open for human intervention."
    fi

    # Set final ticket state
    if [[ ${AUTO_CLOSE} -eq 1 ]]; then
        mark_done
        update_final_status "done"
        bash "${METRICS_SCRIPT}" build_completed ticket_id="${TICKET_ID}" result="done" 2>/dev/null || true
        log "Build complete. Ticket ${TICKET_ID} closed."
    else
        mark_review
        update_final_status "human_review_required"
        bash "${METRICS_SCRIPT}" human_review_required ticket_id="${TICKET_ID}" 2>/dev/null || true
        log "Build complete. Ticket ${TICKET_ID} marked for human review."
    fi

    log "State file: ${STATE_FILE}"
    log "Log file: ${LOG_FILE}"
    log "================================================"
}

main "$@"
