#!/usr/bin/env bash
# Ralph Wiggum Validation Gate v1
# Exits 0 only when ALL quality checks pass.
#
# Ralph Loop Test Policy (ENFORCED):
#   - Default tier is TARGETED (affected modules via detect_affected_tests.py).
#   - e2e and performance tiers are NEVER run in the Ralph loop.
#   - The full test suite is NEVER run in the Ralph loop.
#   - Operator override for e2e/performance: RALPH_ALLOW_E2E=1
#
# Strategy:
#   - pytest tier is configurable: smoke | targeted | integration | full | e2e | performance
#     (default: targeted)
#   - Lint & formatter checks run only on MODIFIED or UNTRACKED files.
#   - e2e and performance tiers are blocked unless RALPH_ALLOW_E2E=1 is set.
#
# Environment variables:
#   RALPH_PROJECT_DIR   - Path to project root
#   RALPH_PYTHON_CMD    - Python executable to use (auto-detected if not set)
#   RALPH_VENV_PATH     - Path to virtual env (default: .venv)
#   RALPH_TEST_DIR      - Root test directory (default: tests)
#   RALPH_ALLOW_E2E     - Set to 1 to allow e2e/performance tiers
#   RALPH_LINT_TOOLS    - Space-separated list of lint tools (default: black isort flake8 mypy)

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

# Parse arguments
TIER="targeted"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tier)
            TIER="$2"
            shift 2
            ;;
        --tier=*)
            TIER="${1#*=}"
            shift
            ;;
        *)
            echo "[RALPH] Unknown argument: $1"
            echo "Valid tiers: smoke, targeted, integration, full, e2e, performance"
            exit 1
            ;;
    esac
done

# --- Ralph Loop Policy Enforcement ---
if [[ "${TIER}" == "e2e" || "${TIER}" == "performance" ]]; then
    if [[ "${RALPH_ALLOW_E2E:-0}" != "1" ]]; then
        echo "[RALPH] ERROR: ${TIER} tier is blocked in the Ralph loop."
        echo "[RALPH] Targeted-tests-only policy enforced."
        echo "[RALPH] Set RALPH_ALLOW_E2E=1 to override (operator-only)."
        exit 1
    fi
fi

# Detect Python environment
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
        echo "[RALPH] ERROR: No Python executable found. Set RALPH_PYTHON_CMD or create a venv at ${VENV_PATH}"
        exit 1
    fi
fi

# Ensure virtual environment is active (if available)
if [[ -z "${VIRTUAL_ENV:-}" && -f "${VENV_PATH}/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${VENV_PATH}/bin/activate"
fi

TEST_DIR="${RALPH_TEST_DIR:-tests}"
FAILED=0
STEP=1
LINT_TOOLS="${RALPH_LINT_TOOLS:-black isort flake8 mypy}"

# Count total steps
TOTAL_STEPS=5

echo "========================================="
echo "[RALPH] Validation Gate Starting..."
echo "[RALPH] Test tier: ${TIER}"
echo "[RALPH] Python: ${PYTHON_CMD}"
echo "[RALPH] Lint tools: ${LINT_TOOLS}"
echo "========================================="

# Determine modified / untracked Python files
MODIFIED_PY=$( (git diff --name-only --diff-filter=ACM && git ls-files --others --exclude-standard) | grep '\.py$' | sort -u || true )

# Override pyproject.toml addopts if needed
PYTEST_ADDOPTS_OVERRIDE=(-o addopts="--tb=short --strict-markers")

# 1. pytest — tiered
case "${TIER}" in
    smoke)
        echo ""
        echo "[${STEP}/${TOTAL_STEPS}] Running SMOKE tests (${TEST_DIR}/unit/ -x -q, unit marker) ..."
        set +e
        ${PYTHON_CMD} -m pytest "${TEST_DIR}/unit/" -x -q --tb=short "${PYTEST_ADDOPTS_OVERRIDE[@]}" -m "unit"
        PYTEST_EXIT=$?
        set -e
        ;;
    targeted|targetted)
        DETECT_SCRIPT="${CORE_DIR:-${PROJECT_DIR}/scripts/ralph}/detect_affected_tests.py"
        if [[ -f "${DETECT_SCRIPT}" ]]; then
            AFFECTED_TESTS=$(${PYTHON_CMD} "${DETECT_SCRIPT}" 2>/dev/null || echo "${TEST_DIR}/unit/")
        else
            AFFECTED_TESTS="${TEST_DIR}/unit/"
        fi
        if [[ -z "${AFFECTED_TESTS}" ]]; then
            echo ""
            echo "[${STEP}/${TOTAL_STEPS}] No affected tests detected. Skipping pytest."
            PYTEST_EXIT=0
        else
            echo ""
            echo "[${STEP}/${TOTAL_STEPS}] Running TARGETED tests: ${AFFECTED_TESTS} ..."
            set +e
            ${PYTHON_CMD} -m pytest ${AFFECTED_TESTS} -q --tb=short "${PYTEST_ADDOPTS_OVERRIDE[@]}" -m "not e2e and not performance"
            PYTEST_EXIT=$?
            set -e
        fi
        ;;
    integration)
        echo ""
        echo "[${STEP}/${TOTAL_STEPS}] Running INTEGRATION tests (${TEST_DIR}/integration/ -q, integration marker) ..."
        set +e
        ${PYTHON_CMD} -m pytest "${TEST_DIR}/integration/" -q --tb=short "${PYTEST_ADDOPTS_OVERRIDE[@]}" -m "integration"
        PYTEST_EXIT=$?
        set -e
        ;;
    full)
        echo ""
        echo "[${STEP}/${TOTAL_STEPS}] Running FULL pytest suite (${TEST_DIR}/ -q, excludes e2e/performance/broker_live) ..."
        set +e
        ${PYTHON_CMD} -m pytest "${TEST_DIR}/" -q --tb=short "${PYTEST_ADDOPTS_OVERRIDE[@]}" -m "not e2e and not performance and not broker_live"
        PYTEST_EXIT=$?
        set -e
        ;;
    e2e)
        echo ""
        echo "[${STEP}/${TOTAL_STEPS}] Running E2E tests (${TEST_DIR}/e2e/ -v) ..."
        set +e
        ${PYTHON_CMD} -m pytest "${TEST_DIR}/e2e/" -v --tb=short "${PYTEST_ADDOPTS_OVERRIDE[@]}"
        PYTEST_EXIT=$?
        set -e
        ;;
    performance)
        echo ""
        echo "[${STEP}/${TOTAL_STEPS}] Running PERFORMANCE tests (${TEST_DIR}/performance/ -v) ..."
        set +e
        ${PYTHON_CMD} -m pytest "${TEST_DIR}/performance/" -v --tb=short "${PYTEST_ADDOPTS_OVERRIDE[@]}"
        PYTEST_EXIT=$?
        set -e
        ;;
    *)
        echo "[RALPH] Unknown tier: ${TIER}"
        echo "Valid tiers: smoke, targeted, integration, full, e2e, performance"
        exit 1
        ;;
esac

# Handle pytest result
if [[ ${PYTEST_EXIT} -eq 0 ]]; then
    echo "[${STEP}/${TOTAL_STEPS}] pytest ${TIER} PASSED"
elif [[ ${PYTEST_EXIT} -eq 5 ]]; then
    echo "[${STEP}/${TOTAL_STEPS}] pytest ${TIER} PASSED (no tests collected — all deselected or none match filter)"
else
    echo "[${STEP}/${TOTAL_STEPS}] pytest ${TIER} FAILED"
    FAILED=1
fi
STEP=$((STEP + 1))

if [[ -n "${MODIFIED_PY}" ]]; then
    echo ""
    echo "[RALPH] Modified/untracked Python files detected:"
    echo "${MODIFIED_PY}"
    echo ""

    # Run each lint tool
    for TOOL in ${LINT_TOOLS}; do
        case "${TOOL}" in
            black)
                echo "[${STEP}/${TOTAL_STEPS}] Running black --check on modified files ..."
                if echo "${MODIFIED_PY}" | xargs ${PYTHON_CMD} -m black --check 2>/dev/null; then
                    echo "[${STEP}/${TOTAL_STEPS}] black PASSED"
                else
                    echo "[${STEP}/${TOTAL_STEPS}] black FAILED"
                    FAILED=1
                fi
                ;;
            isort)
                echo ""
                echo "[${STEP}/${TOTAL_STEPS}] Running isort --check-only on modified files ..."
                if echo "${MODIFIED_PY}" | xargs ${PYTHON_CMD} -m isort --check-only 2>/dev/null; then
                    echo "[${STEP}/${TOTAL_STEPS}] isort PASSED"
                else
                    echo "[${STEP}/${TOTAL_STEPS}] isort FAILED"
                    FAILED=1
                fi
                ;;
            flake8)
                echo ""
                echo "[${STEP}/${TOTAL_STEPS}] Running flake8 on modified files ..."
                if echo "${MODIFIED_PY}" | xargs ${PYTHON_CMD} -m flake8 2>/dev/null; then
                    echo "[${STEP}/${TOTAL_STEPS}] flake8 PASSED"
                else
                    echo "[${STEP}/${TOTAL_STEPS}] flake8 FAILED"
                    FAILED=1
                fi
                ;;
            mypy)
                echo ""
                echo "[${STEP}/${TOTAL_STEPS}] Running mypy on modified files ..."
                MYPY_MODULES=""
                for f in ${MODIFIED_PY}; do
                    if [[ "$f" == *.py ]]; then
                        if [[ "$f" == *__init__.py ]]; then
                            mod=$(echo "$f" | sed 's|^src/||' | sed 's|/|.|g' | sed 's|\.\_\_init\_\_\.py$||')
                        else
                            mod=$(echo "$f" | sed 's|^src/||' | sed 's|/|.|g' | sed 's|\.py$||')
                        fi
                        MYPY_MODULES="${MYPY_MODULES} -m ${mod}"
                    fi
                done
                if ${PYTHON_CMD} -m mypy --follow-imports=silent ${MYPY_MODULES} 2>/dev/null; then
                    echo "[${STEP}/${TOTAL_STEPS}] mypy PASSED"
                else
                    echo "[${STEP}/${TOTAL_STEPS}] mypy FAILED"
                    FAILED=1
                fi
                ;;
            ruff)
                echo ""
                echo "[${STEP}/${TOTAL_STEPS}] Running ruff on modified files ..."
                if echo "${MODIFIED_PY}" | xargs ${PYTHON_CMD} -m ruff check 2>/dev/null; then
                    echo "[${STEP}/${TOTAL_STEPS}] ruff PASSED"
                else
                    echo "[${STEP}/${TOTAL_STEPS}] ruff FAILED"
                    FAILED=1
                fi
                ;;
            *)
                echo ""
                echo "[${STEP}/${TOTAL_STEPS}] Skipping unknown lint tool: ${TOOL}"
                ;;
        esac
        STEP=$((STEP + 1))
    done
else
    echo ""
    echo "[RALPH] No modified/untracked Python files detected."
    echo "[RALPH] Skipping targeted lint/formatter checks."
fi

echo ""
echo "========================================="
if [[ ${FAILED} -eq 0 ]]; then
    echo "RALPH_GATE_PASSED"
    echo "========================================="
    exit 0
else
    echo "RALPH_GATE_FAILED"
    echo "========================================="
    exit 1
fi
