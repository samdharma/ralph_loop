# Ralph Wiggum Loop Build System

> *"I'm helping!"* — Ralph Wiggum

An **AI-agent-powered continuous build loop** that turns your beads ticket queue into working,
tested, committed code — one iteration at a time. No more context-switching. No more forgotten
tickets. Just `ralph init` and let the loop build your project.

---

## Architecture: Global Tool, Thin Projects

Ralph is a **global CLI tool** installed at `~/.ralph/`. Core build scripts live there.
Your project carries **only config files** — no build system scripts in your repo.

```
~/.ralph/                          ← Global install (one per system)
├── core/                          ← 12 build scripts live HERE
├── templates/                     ← Project scaffolding templates
└── bin/ralph                      ← CLI entry point

my-project/                        ← Your GitHub repo (clean!)
├── .ralph/config.toml             ← Project config (committed)
├── AGENTS.md                      ← Project rules (committed)
├── config/
│   ├── ralph_preflight.sh         ← Your guardrails (committed)
│   └── TEST_MAP.yaml              ← Test mapping (committed)
├── docs/agent/
│   ├── PROMPT.md                  ← Agent context (committed)
│   └── PROGRESS.md                ← Auto-updated (gitignored)
├── src/                           ← Your code
└── tests/                         ← Your tests
```

**What someone clones:** just your code + config files. No Ralph build scripts.
They install Ralph once globally, then `cd` into any Ralph project and run `ralph daemon`.

---

## How Ralph Works

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

## Setting Up on a New System

### Prerequisites

- **bash** 4+ (macOS/Linux)
- **Python** 3.10+
- **git**
- **[beads](https://github.com/beadsboard/beads)** (`bd`) — issue tracker (Ralph requires beads for ticket management)
- **kimi** or **pi** — at least one AI agent CLI

### Install Ralph Globally

```bash
# Clone Ralph to ~/.ralph
git clone https://github.com/samdharma/Ralph_loop.git ~/.ralph

# Run the installer (creates symlink, sets RALPH_HOME)
bash ~/.ralph/scripts/install.sh

# Reload your shell
source ~/.zshrc    # or source ~/.bashrc

# Verify
ralph version      # → ralph v1.0.0
```

### Clone an Existing Ralph Project

```bash
# Clone the project — it has NO Ralph build scripts, only config
git clone https://github.com/your-org/my-trading-bot.git
cd my-trading-bot

# One command: initializes beads, syncs ticket data, checks everything
ralph setup

# Start building
ralph daemon
```

That's it. `ralph setup` handles everything — no manual `bd init`, no `bd dolt pull`.

### Create a New Project

```bash
ralph init
```

Answer 7 questions. Ralph scaffolds:
- `.ralph/config.toml` — project configuration (committed to repo)
- `AGENTS.md` — project rules and conventions
- `docs/agent/PROMPT.md` — agent prompt (customize this!)
- `config/ralph_preflight.sh` — guardrail rules
- `config/TEST_MAP.yaml` — source-to-test mappings
- `.gitignore` — ignores Ralph runtime artifacts
- Git + Beads initialized

**No build scripts are copied into the project.** Ralph scripts live in `~/.ralph/core/` and
are invoked via the global `ralph` CLI.

---

## Project Structure (after `ralph init`)

```
my-project/
├── .ralph/
│   └── config.toml              # ← Single source of truth (committed)
├── AGENTS.md                    # ← Project rules (committed)
├── .gitignore                   # ← Ignores runtime artifacts only
├── config/
│   ├── ralph_preflight.sh       # ← Your guardrail rules (committed)
│   └── TEST_MAP.yaml            # ← Source → test file mappings (committed)
├── docs/
│   └── agent/
│       ├── PROMPT.md            # ← Agent prompt — customize this! (committed)
│       ├── PROGRESS.md          # ← Auto-updated iteration log (gitignored)
│       └── prompts/             # ← Type-specific guidance (bugfix, docs, etc.)
├── src/                         # ← Your source code
├── tests/                       # ← Your test suite
└── logs/                        # ← Ralph metrics + loop logs (gitignored)
```

**What's NOT in the repo:** `scripts/ralph/` with 12 build scripts. They're in `~/.ralph/core/`.

---

## Commands (Global CLI)

```bash
# Initialize a new project (beads included)
ralph init

# Post-clone setup (beads init + dolt pull in one command)
ralph setup

# Run the build loop (foreground, single ticket mode)
ralph loop --ticket=<id> --agent=pi

# 3-Session Pipeline (recommended for quality)
ralph design --ticket=<id> --agent=pi     # Session 1: Plan (no code)
ralph implement --ticket=<id> --agent=pi  # Session 2: Write code
ralph verify --ticket=<id> --agent=pi     # Session 3: Validate & close

# Run the build loop (foreground, continuous)
ralph loop

# Run as background daemon (recommended for batch)
ralph daemon

# Run validation gate on current work
ralph validate --tier=targeted

# Check loop health
ralph health --verbose

# Generate daily/weekly report
ralph report --daily

# Project dashboard
ralph status

# Convert legacy project to new config format
ralph migrate
```

### Loop Options

| Flag | Description |
|------|-------------|
| `--ticket=<id>` | Run a single ticket and exit |
| `--agent=kimi\|pi` | Specify AI agent (Pi supports DeepSeek, Kimi supports k2.6) |
| `--tier=smoke\|targeted\|integration\|full` | Test tier (default: targeted) |
| `--tag=<tag>` | Filter tickets by label (e.g., `--tag=phase-1`) |
| `--force` | Skip dirty-worktree check |

**Remote Sync (Hotfix Integration):** Ralph automatically fetches from
origin before each iteration (configurable via `RALPH_REMOTE_SYNC_INTERVAL_SEC`,
default: 300s). If a hotfix is detected (local behind remote), it auto-rebases.
If the branch has diverged, it halts and alerts for manual triage.
Set `RALPH_REMOTE_SYNC=0` to disable. Use `ralph sync` to check manually.

### Validate Options

```
ralph validate --tier=smoke        # Fastest (unit tests, fail-fast)
ralph validate --tier=targeted     # Only affected tests (default)
ralph validate --tier=integration  # Integration tests
ralph validate --tier=full         # All tests except e2e/perf (operator only)
```

---

## Comparison: Before vs After

| Aspect | Before (Embedded) | After (Global Tool) |
|--------|-------------------|---------------------|
| **Build scripts in repo** | 12 scripts in `scripts/ralph/` | Zero (in `~/.ralph/core/`) |
| **Git noise on Ralph updates** | Every project changes | One global update |
| **Clone & build** | Clone, install Ralph, hope versions match | Clone, `ralph daemon` |
| **Commands** | `bash scripts/ralph/ralph_loop.sh` | `ralph loop` |
| **Config** | Scattered across scripts, env vars | `.ralph/config.toml` |
| **CI/CD pollution** | Ralph scripts in CI context | No Ralph in CI (dev tool only) |

---

## Migration: Legacy → New Format

If you have an existing project with `scripts/ralph/`:

```bash
cd your-project
ralph migrate
```

This:
- Creates `.ralph/config.toml` from your existing setup
- Updates `AGENTS.md` and `PROMPT.md` to use `ralph` commands
- You can then `rm -rf scripts/ralph/` to clean up

---

## Roadmap

| Phase | Status |
|-------|--------|
| Phase 1 — Extract & Clean | ✅ Complete |
| Phase 2 — `ralph init` Wizard | ✅ Complete |
| Phase 3 — Documentation & Polish | ✅ Complete |
| Phase 4 — Global Tool Decoupling | ✅ Complete |

---

## Documentation

### 📖 HTML (Recommended — Open in Browser)

**[`docs/ralph_documentation.html`](docs/ralph_documentation.html)** — Complete single-page documentation with:
- GitHub dark theme
- Mermaid.js diagrams and flowcharts
- Sidebar navigation, search-friendly headings, responsive layout

### 📝 Markdown

| Doc | Topic |
|-----|-------|
| [BUILD_SYSTEM_OVERVIEW.md](docs/BUILD_SYSTEM_OVERVIEW.md) | Layman-friendly explanation |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | New system setup |
| [GETTING_STARTED.md](docs/GETTING_STARTED.md) | First project walkthrough |
| [DAILY_USAGE.md](docs/DAILY_USAGE.md) | Day-to-day workflow |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Failure scenarios, recovery |
| [TICKET_MANAGEMENT.md](docs/TICKET_MANAGEMENT.md) | Beads workflow |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | All environment variables |
| [FAQ.md](docs/FAQ.md) | Common questions |

---

## License

MIT
