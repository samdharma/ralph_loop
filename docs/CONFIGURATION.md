# Configuration — All Environment Variables

> Every env var Ralph reads, what it does, and its default.

---

## Ralph Core Configuration

These env vars control the behavior of the Ralph loop harness itself.

### Loop Harness (`ralph_loop.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | `$(cd scripts/ralph/../.. && pwd)` | Path to project root |
| `RALPH_CORE_DIR` | Auto-detected from script location | Path to ralph core scripts |
| `RALPH_PROMPT_BASE` | `docs/agent/PROMPT.md` | Path to base agent prompt |
| `RALPH_PROMPT_DIR` | `docs/agent/prompts` | Directory for type-specific prompt extensions |
| `RALPH_PROGRESS_FILE` | `docs/agent/PROGRESS.md` | Path to progress log |
| `RALPH_CHECKPOINT` | `.ralph_checkpoint.json` | Path to checkpoint file |
| `RALPH_LOG_DIR` | `logs` | Directory for loop logs |
| `RALPH_ALLOW_E2E` | `0` | Set to `1` to allow e2e/performance test tiers |
| `RALPH_METRICS_FILE` | `logs/ralph_metrics.jsonl` | Path to metrics JSONL file |
| `RALPH_PREFLIGHT_SCRIPT` | `~/.ralph/core/ralph_preflight.sh` | Override preflight script path |
| `RALPH_VALIDATE_SCRIPT` | `~/.ralph/core/ralph_validate.sh` | Override validate script path |
| `RALPH_METRICS_SCRIPT` | `~/.ralph/core/ralph_metrics.sh` | Override metrics script path |
| `RALPH_LOOP_SCRIPT` | `~/.ralph/core/ralph_loop.sh` | Override loop script path (for daemon) |
| `RALPH_REMOTE_SYNC` | `1` | Set to `0` to disable pre-iteration remote sync |
| `RALPH_REMOTE_SYNC_INTERVAL_SEC` | `300` (5 min) | Minimum seconds between `git fetch` checks |

### Daemon (`run_ralph_loop.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root directory |

### Preflight (`ralph_preflight.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_PREFLIGHT_EXTRA` | (none) | Path to additional preflight script to source |

### Validation Gate (`ralph_validate.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_PYTHON_CMD` | Auto-detected from venv/PATH | Python executable |
| `RALPH_VENV_PATH` | `.venv` | Virtual environment directory |
| `RALPH_TEST_DIR` | `tests` | Root test directory |
| `RALPH_ALLOW_E2E` | `0` | Allow e2e/performance tiers |
| `RALPH_LINT_TOOLS` | `black isort flake8 mypy` | Space-separated lint tools to run |

### Health Check (`ralph_health.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_METRICS_FILE` | `logs/ralph_metrics.jsonl` | Metrics file to check |
| `RALPH_CHECKPOINT` | `.ralph_checkpoint.json` | Checkpoint file to check |
| `RALPH_MAX_METRICS_AGE_SEC` | `7200` (2 hours) | Max age before metrics considered stale |
| `RALPH_MAX_CHECKPOINT_AGE_SEC` | `1800` (30 minutes) | Max age before checkpoint considered crashed |

> **Remote sync note:** The health check (#4) also detects remote divergence.
> The loop's new `sync_with_remote()` gate (RALPH_REMOTE_SYNC=1) automatically
> fetches, detects hotfixes, and auto-rebases before each iteration.
> Use `ralph sync` to manually check remote status.

### Metrics Logger (`ralph_metrics.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_METRICS_FILE` | `logs/ralph_metrics.jsonl` | Metrics output path |

### Report Generator (`ralph_report.sh` / `.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_METRICS_FILE` | `logs/ralph_metrics.jsonl` | Input metrics file |
| `RALPH_PYTHON_CMD` | Auto-detected | Python executable |
| `RALPH_VENV_PATH` | `.venv` | Virtual environment path |

### Spec Checker (`ralph_check_specs.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_SPEC_PATH` | `docs/agent/SPEC.md` | Path to spec markdown |
| `RALPH_REPORT_PATH` | `docs/agent/spec_report.json` | Path to JSON report output |

### Performance Gate (`ralph_performance_check.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_PYTHON_CMD` | Auto-detected | Python executable |
| `RALPH_VENV_PATH` | `.venv` | Virtual environment |
| `RALPH_TEST_DIR` | `tests` | Test directory root |

### Test Mapper (`detect_affected_tests.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | Auto-detected | Project root |
| `RALPH_TEST_MAP` | `config/TEST_MAP.yaml` | Path to test map YAML |

---

## How to Set Variables

### Per-Project (Recommended)

Add to your project's `.env` file (or a `config/ralph_env.sh`):

```bash
# .env
export RALPH_ALLOW_E2E=0
export RALPH_LINT_TOOLS="black isort flake8 mypy"
```

### Per-Session

```bash
RALPH_ALLOW_E2E=1 bash scripts/ralph/ralph_validate.sh --tier=e2e
```

### Global (Shell Profile)

```bash
# ~/.zshrc
export RALPH_LINT_TOOLS="ruff mypy"
```

---

## Ralph Home Configuration

These are set by `install.sh`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_HOME` | `$HOME/.ralph` | Where Ralph is installed |
| `PATH` | Includes `/usr/local/bin` or `~/.local/bin` | Where `ralph` CLI symlink lives |
