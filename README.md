# Ralph Wiggum Loop Build System

> *"I'm helping!"* — Ralph Wiggum

An **AI-agent-powered continuous build loop** that turns your beads ticket queue into working,
tested, committed code — one iteration at a time. No more context-switching. No more forgotten
tickets. Just `ralph init` and let the loop build your project.

---

## What Ralph Does

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ bd ready │ →  │ PREFLIGHT│ →  │  AGENT   │ →  │VALIDATE  │
│ (queue)  │    │ (guard)  │    │ (kimi/pi)│    │ (gate)   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                    │
                                               ┌────▼────┐
                                               │ COMMIT  │
                                               │ & REPEAT│
                                               └─────────┘
```

1. **Pulls** the next ready ticket from your [beads](https://github.com/beadsboard/beads) queue
2. **Preflights** — skips blocked/wrong-time tickets via configurable guardrails
3. **Assembles** an adaptive prompt (base + type-specific + phase-reference-doc + task context)
4. **Invokes** your AI agent (`kimi` or `pi`) in non-interactive mode to implement the task
5. **Validates** — runs tests + lint + type-check only on changed files
6. **Commits** if clean, checkpoints if dirty, then loops to the next ticket

---

## Quick Start

### Prerequisites

- **bash** 4+ (macOS/Linux)
- **Python** 3.10+
- **git**
- **[beads](https://github.com/beadsboard/beads)** (`bd`) — issue tracker
- **kimi** or **pi** — at least one AI agent CLI

### Install

```bash
# Clone
git clone https://github.com/samdharma/Ralph_loop.git ~/.ralph

# Install (creates symlink, sets RALPH_HOME)
bash ~/.ralph/scripts/install.sh

# Verify
ralph version
```

### Create Your First Project

```bash
ralph init
```

Answer 7 questions. Ralph scaffolds:
- Git + Beads initialized
- 12 core scripts in `scripts/ralph/`
- `AGENTS.md`, `.gitignore`, prompt templates, preflight config, test map

### Start Building

```bash
cd your-project
bash scripts/ralph/run_ralph_loop.sh    # Background daemon
# or
bash scripts/ralph/ralph_loop.sh --ticket=<id> --agent=kimi  # Single-shot
```

---

## Documentation

### 📖 HTML (Recommended — Open in Browser)

**[`docs/html/index.html`](docs/html/index.html)** — Complete single-page documentation with:
- GitHub dark theme (no bright backgrounds, optimized for screen reading)
- Mermaid.js diagrams, flowcharts, and sequence diagrams
- Sidebar navigation, search-friendly headings, responsive layout

### 📝 Markdown

| Doc | Topic |
|-----|-------|
| [BUILD_SYSTEM_OVERVIEW.md](docs/BUILD_SYSTEM_OVERVIEW.md) | Layman-friendly explanation of what Ralph is and does |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, component diagram |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | New computer setup — high level & step-by-step |
| [GETTING_STARTED.md](docs/GETTING_STARTED.md) | First project after install — complete walkthrough |
| [DAILY_USAGE.md](docs/DAILY_USAGE.md) | Day-to-day building, must-have files, app specs |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Failure scenarios, monitoring, cleanup, restart |
| [TICKET_MANAGEMENT.md](docs/TICKET_MANAGEMENT.md) | Naming rules, beads workflow, monitoring |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | All environment variables and their defaults |
| [FAQ.md](docs/FAQ.md) | Common questions and answers |

---

## Project Structure (after `ralph init`)

```
my-project/
├── AGENTS.md                  # Project rules + Ralph quick reference
├── .gitignore                 # Secrets, artifacts, Ralph runtime files
├── config/
│   ├── ralph_preflight.sh     # Your guardrail rules
│   └── TEST_MAP.yaml          # Source → test file mappings
├── docs/
│   ├── agent/
│   │   ├── PROMPT.md          # Base agent prompt (customize this!)
│   │   ├── PROGRESS.md        # Auto-updated iteration log
│   │   └── prompts/           # Type-specific guidance (bugfix, docs, etc.)
│   └── reference/             # Your phase build docs go here
├── scripts/
│   └── ralph/                 # 12 Ralph core scripts
├── src/                       # Your source code
├── tests/                     # Your test suite
└── logs/                      # Ralph metrics + loop logs
```

---

## Commands (inside a Ralph project)

```bash
# Loop (background daemon, one instance at a time)
bash scripts/ralph/run_ralph_loop.sh

# Loop (foreground, single ticket)
bash scripts/ralph/ralph_loop.sh --ticket=<id> --agent=kimi

# Validate current work (tests + lint + type-check)
bash scripts/ralph/ralph_validate.sh --tier=targeted

# Check loop health
bash scripts/ralph/ralph_health.sh --verbose

# Generate daily/weekly report
bash scripts/ralph/ralph_report.sh --daily
```

---

## CLI Reference

```bash
ralph init       # Scaffold a new project
ralph status     # Health dashboard for current project
ralph version    # Show version
ralph help       # Show this help
```

---

## Roadmap

| Phase | Status |
|-------|--------|
| Phase 1 — Extract & Clean | ✅ Complete |
| Phase 2 — `ralph init` Wizard | ✅ Complete |
| Phase 3 — Documentation & Polish | 🚧 In Progress |

See `PHASE_1_ROADMAP.md`, `PHASE_2_ROADMAP.md`, `PHASE_3_ROADMAP.md`.

---

## License

MIT
