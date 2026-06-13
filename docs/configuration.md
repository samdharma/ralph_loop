# Configuration — Environment Variables

> Every env var Ralph reads, what it does, and its default.

---

## Core Configuration

These env vars control the behavior of the Ralph loop harness.

### Loop Harness (`ralph_loop.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | current working directory | Path to project root |
| `RALPH_CORE_DIR` | auto-detected from `~/.ralph/core/` | Path to Ralph core scripts |
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
| `RALPH_REMOTE_SYNC` | `1` | Set to `0` to disable pre-iteration remote sync |
| `RALPH_REMOTE_SYNC_INTERVAL_SEC` | `300` (5 min) | Minimum seconds between `git fetch` checks |

### Daemon (`run_ralph_loop.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | auto-detected | Project root directory |

### Preflight (`ralph_preflight.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | auto-detected | Project root |
| `RALPH_PREFLIGHT_EXTRA` | (none) | Path to additional preflight script to source |

### Validation Gate (`ralph_validate.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | auto-detected | Project root |
| `RALPH_PYTHON_CMD` | auto-detected from venv/PATH | Python executable |
| `RALPH_VENV_PATH` | `.venv` | Virtual environment directory |
| `RALPH_TEST_DIR` | `tests` | Root test directory |
| `RALPH_ALLOW_E2E` | `0` | Allow e2e/performance tiers |
| `RALPH_LINT_TOOLS` | `black isort flake8 mypy` | Space-separated lint tools |

### Health Check (`ralph_health.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | auto-detected | Project root |
| `RALPH_METRICS_FILE` | `logs/ralph_metrics.jsonl` | Metrics file to check |
| `RALPH_CHECKPOINT` | `.ralph_checkpoint.json` | Checkpoint file to check |
| `RALPH_MAX_METRICS_AGE_SEC` | `7200` (2 hours) | Max age before metrics considered stale |
| `RALPH_MAX_CHECKPOINT_AGE_SEC` | `1800` (30 minutes) | Max age before checkpoint considered crashed |

### Metrics Logger (`ralph_metrics.sh`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | auto-detected | Project root |
| `RALPH_METRICS_FILE` | `logs/ralph_metrics.jsonl` | Metrics output path |

### Report Generator

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | auto-detected | Project root |
| `RALPH_METRICS_FILE` | `logs/ralph_metrics.jsonl` | Input metrics file |
| `RALPH_PYTHON_CMD` | auto-detected | Python executable |
| `RALPH_VENV_PATH` | `.venv` | Virtual environment path |

### Test Mapper (`detect_affected_tests.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PROJECT_DIR` | auto-detected | Project root |
| `RALPH_TEST_MAP` | `config/TEST_MAP.yaml` | Path to test map YAML |

---

## How to Set Variables

### Per-Project (Recommended)

Add to your project's `.env` file:

```bash
export RALPH_ALLOW_E2E=0
export RALPH_LINT_TOOLS="black isort flake8 mypy"
```

### Per-Session

```bash
RALPH_ALLOW_E2E=1 ralph validate --tier=e2e
```

### Global (Shell Profile)

```bash
# ~/.zshrc
export RALPH_LINT_TOOLS="ruff mypy"
```

---

## Ralph Home Configuration

Set by `install.sh`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_HOME` | `$HOME/.ralph` | Where Ralph is installed |
| `PATH` | includes `/usr/local/bin` or `~/.local/bin` | Where `ralph` CLI symlink lives |
