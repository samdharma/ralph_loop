# Phase 1 — Extract & Clean Core

**Goal**: Extract the Ralph Wiggum Loop build system from SAM Trader V3 into a standalone,
fully decoupled repository. Nothing of SAM Trader remains.

**Status**: ✅ COMPLETE

---

## 1.1 Repository Scaffold

Create the `ralph/` repo with this structure:

```
ralph/
├── bin/
│   └── ralph                  # CLI entry point (added in Phase 2)
├── core/                      # Generic scripts — never user-edited
│   ├── ralph_loop.sh          # Main agentic loop harness
│   ├── run_ralph_loop.sh      # PID-file daemon wrapper
│   ├── ralph_preflight.sh     # Guardrail system (sources project config)
│   ├── ralph_validate.sh      # Validation gate (Python only for now)
│   ├── ralph_health.sh        # Health checker (5 checks)
│   ├── ralph_metrics.sh       # JSONL metrics logger
│   ├── ralph_metrics_viewer.py
│   ├── ralph_report.sh        # Daily/weekly report shell wrapper
│   ├── ralph_report.py        # Daily/weekly report Python implementation
│   ├── ralph_check_specs.py   # SPEC.md verification runner
│   ├── ralph_performance_check.sh
│   └── detect_affected_tests.py
├── templates/                 # Jinja2-style templates for `ralph init`
│   ├── AGENTS.md.j2
│   ├── PROMPT.md.j2
│   ├── PROGRESS.md.j2
│   ├── prompts/
│   │   ├── bugfix.md
│   │   ├── docs.md
│   │   ├── feature.md
│   │   ├── ops.md
│   │   └── regression_test.md
│   ├── ralph_preflight.sh.j2
│   ├── TEST_MAP.yaml.j2
│   └── gitignore.j2
├── scripts/                   # Install helpers
│   └── install.sh             # Symlink ralph CLI to /usr/local/bin
├── init.py                    # Interactive Q&A wizard (Phase 2)
├── README.md                  # Quick start guide
├── PHASE_1_ROADMAP.md         # This file
├── PHASE_2_ROADMAP.md
└── PHASE_3_ROADMAP.md
```

## 1.2 Core Scripts — Cleaning Rules

For each script copied from `sam_trader/scripts/ralph/`:

| Rule | Description |
|------|-------------|
| **R1** | Remove all `sam_trader`, `SAM Trader`, `csam_trader` references |
| **R2** | Replace hardcoded paths with `${RALPH_CORE_DIR}` or `${PROJECT_DIR}` |
| **R3** | Replace `PROJECT_DIR="$(cd .../../.."` with `PROJECT_DIR="${RALPH_PROJECT_DIR:-$(pwd)}"` |
| **R4** | Add `RALPH_CORE_DIR` env var pointing to the core scripts directory |
| **R5** | Keep all env-var parameterization intact |
| **R6** | Strip SAM Trader-specific defaults from comments |

## 1.3 Scripts to Port (from sam_trader/scripts/ralph/)

### Fully Generic — Copy with minimal cleanup

| Source File | Dest File | Changes |
|-------------|-----------|---------|
| `ralph_loop.sh` | `core/ralph_loop.sh` | R1-R6. Make PROMPT.md path relative to PROJECT_DIR. Add `RALPH_LOOP_SCRIPT` env override for the preflight/validate/metrics scripts so users can swap them. |
| `run_ralph_loop.sh` | `core/run_ralph_loop.sh` | R1-R4. Generic daemon wrapper. |
| `ralph_preflight.sh` | `core/ralph_preflight.sh` | R1-R4. Already well-designed with sourcing pattern. |
| `ralph_health.sh` | `core/ralph_health.sh` | R1-R3. Already fully generic. |
| `ralph_metrics.sh` | `core/ralph_metrics.sh` | R1-R3. Already fully generic. |
| `ralph_metrics_viewer.py` | `core/ralph_metrics_viewer.py` | R1-R3. Already generic. |
| `ralph_report.sh` | `core/ralph_report.sh` | R1-R3. Already generic. |
| `ralph_report.py` | `core/ralph_report.py` | R1-R3. Already generic. |
| `ralph_check_specs.py` | `core/ralph_check_specs.py` | R1-R3. Already generic. |
| `ralph_performance_check.sh` | `core/ralph_performance_check.sh` | R1-R3. Python-centric but generic. |

### Partially Generic — Needs refactoring

| Source File | Dest File | Changes |
|-------------|-----------|---------|
| `ralph_validate.sh` | `core/ralph_validate.sh` | R1-R6. Rename to `ralph_validate.sh`. Add `RALPH_LINT_TOOLS` env to allow swapping lint/formatter commands. Add `RALPH_TEST_RUNNER` env for non-pytest test runners. |
| `detect_affected_tests.py` | `core/detect_affected_tests.py` | R1-R3. Add `RALPH_TEST_MAP` env support (already has it). |

### NOT Ported (SAM Trader specific)

- `validate_actors.sh` — Docker + Futu + PostgreSQL specific
- `validate_env_hostnames.sh` — Docker Compose service name checks
- `validate_ib_stack.sh` — IB Gateway + Nautilus specific
- `validate_restart.sh` — Docker + OrbStrategy specific
- `monitor_phase3.sh` — Phase-specific ticket monitoring

## 1.4 Templates — What Gets Templatized

Each `.j2` template uses `{{ VARIABLE }}` syntax. Variables come from the init wizard (Phase 2).

### Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `PROJECT_NAME` | Human-readable project name | "My Trading Bot" |
| `PROJECT_SLUG` | Lowercase kebab-case slug | "my-trading-bot" |
| `PROJECT_PACKAGE` | Python package name (snake_case) | "my_trading_bot" |
| `PROJECT_DESCRIPTION` | 1-2 sentence project description | "Autonomous trading bot..." |
| `PROJECT_LANGUAGE` | Primary language | "python" / "node" / "go" |
| `PROJECT_ROOT` | Absolute path to project dir | "/Users/.../my-project" |
| `AGENT_CMD` | Preferred AI agent | "kimi" / "pi" |
| `TEST_FRAMEWORK` | Test runner | "pytest" / "jest" / "go test" |
| `TEST_DIR` | Test directory | "tests" / "__tests__" / "test" |
| `LINT_TOOLS` | Space-separated lint tools | "black isort flake8 mypy" |
| `RALPH_VERSION` | Build system version | "1.0.0" |
| `INIT_DATE` | ISO date of init | "2026-05-24" |

## 1.5 Deliverables

- [x] `PHASE_1_ROADMAP.md` — this file
- [x] `core/ralph_loop.sh` — cleaned, generalized
- [x] `core/run_ralph_loop.sh` — cleaned
- [x] `core/ralph_preflight.sh` — cleaned
- [x] `core/ralph_validate.sh` — cleaned, generalized
- [x] `core/ralph_health.sh` — cleaned
- [x] `core/ralph_metrics.sh` — cleaned
- [x] `core/ralph_metrics_viewer.py` — cleaned
- [x] `core/ralph_report.sh` — cleaned
- [x] `core/ralph_report.py` — cleaned
- [x] `core/ralph_check_specs.py` — cleaned
- [x] `core/ralph_performance_check.sh` — cleaned
- [x] `core/detect_affected_tests.py` — cleaned
- [x] `templates/AGENTS.md.j2`
- [x] `templates/PROMPT.md.j2`
- [x] `templates/PROGRESS.md.j2`
- [x] `templates/prompts/bugfix.md`
- [x] `templates/prompts/docs.md`
- [x] `templates/prompts/feature.md`
- [x] `templates/prompts/ops.md`
- [x] `templates/prompts/regression_test.md`
- [x] `templates/ralph_preflight.sh.j2`
- [x] `templates/TEST_MAP.yaml.j2`
- [x] `templates/gitignore.j2`
