# Ralph v3 — Automated Build System

> AI-agent-powered continuous build loop. GitHub Issues are tickets, labels are
> status, the Kanban board is your dashboard. No databases. Just `git` and `gh`.

```mermaid
flowchart LR
    A[status:ready] --> B[DESIGN<br/>research + spec]
    B --> C[BUILD<br/>test + code]
    C --> D[VERIFY<br/>review]
    D -->|pass| E[status:review]
    D -->|fail| F[status:blocked]
    F -.->|retry label| C
    F -.->|retry label| D
```

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/samdharma/Ralph_loop/ralph-v3/scripts/install.sh | bash
source ~/.zshrc
ralph version   # → ralph v3.0.0
```

Requires: **git**, **gh**, **python 3.10+**, and **pi** or **kimi**.

## Quick Start

```bash
# Create a new project
ralph init my-project --create-labels

# Or init an existing repo
cd your-repo && ralph init --create-labels

# Verify everything
ralph setup

# Create a GitHub issue with label status:ready, then:
ralph daemon              # continuous loop
ralph daemon --issue 42   # single issue
```

## How It Works

Ralph runs a **3-stage pipeline** for each `status:ready` issue:

| Stage | What happens | Label |
|-------|-------------|-------|
| **DESIGN** | Agent researches codebase, writes design spec to `PROGRESS.md`. Posts summary as issue comment. | `status:design` |
| **BUILD** | Two sub-agents: TEST writes tests from spec (isolated), IMPLEMENT writes code to pass them. | `status:build` |
| **VERIFY** | Fresh isolated reviewer checks diff against spec + issue. 5-axis review. | `status:verify` |

**On success:** issue → `status:review` (your turn to inspect and close).
**On failure:** issue → `status:blocked` with a detailed comment pointing to artifacts.

### Retry After a Failure

Fix the problem, then re-queue with a retry label — no need to re-run earlier stages:

| Label | What it re-runs |
|-------|----------------|
| `status:verify-retry` | VERIFY only |
| `status:build-retry` | BUILD → VERIFY |
| `status:ready` | Full pipeline (DESIGN → BUILD → VERIFY) |

## Commands

| Command | Purpose |
|---------|---------|
| `ralph init [dir]` | Scaffold a Ralph project |
| `ralph setup` | Check prerequisites (gh auth, labels, deps) |
| `ralph daemon [--auto-close] [--issue=N] [--pi-flag=FLAG]` | Start the build loop |
| `ralph status` | Show daemon PID, active issue, recent metrics |
| `ralph validate [--tier=...]` | Run the validation gate (pytest + lint) |
| `ralph report` | Generate daily/weekly summary |

## Project Layout

```
my-project/
├── .ralph/config.toml        # Project config
├── config/
│   ├── ralph_preflight.sh    # Pre-flight guardrails
│   └── TEST_MAP.yaml         # Source → test mapping
├── docs/agent/
│   ├── PROMPT.md             # Base agent rules
│   ├── PROGRESS.md           # Design spec (Ralph artifact)
│   └── prompts/              # Stage personas (design, test, implement, verify)
├── src/                      # Application source
├── tests/                    # Unit + integration tests
├── AGENTS.md                 # Quick reference for agents
└── .gitignore
```

## Documentation

| Document | Topic |
|----------|-------|
| [Getting Started](docs/getting_started.md) | Full guide: install, setup, tickets, pipeline, observability |
| [Observability](docs/observability.md) | Monitoring: metrics, dashboards, external tools |
| [v3 Redesign](docs/v3-redesign.md) | System design, phases, build notes (for Ralph developers) |

## License

MIT

*Last updated: 2026-06-21. --pi-flag, --no-skills, rule #7 relaxed for external review tools.*
