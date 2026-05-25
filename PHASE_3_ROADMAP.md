# Phase 3 — Polish, Document, & Ship

**Goal**: Make the Ralph Wiggum Loop Build System production-ready with
comprehensive documentation, install automation, and project health features.

**Status**: ✅ COMPLETE

---

## 3.1 Documentation

### README.md

Complete quick-start guide covering:
- What is Ralph? (1 paragraph)
- Prerequisites (bash 4+, python 3.10+, git, beads (bd), kimi or pi)
- Install (clone + `bash scripts/install.sh`)
- Quick start (`ralph init`, answer questions, `bash scripts/ralph/run_ralph_loop.sh`)
- Project structure after init
- Core concepts (loop, preflight, validation gate, checkpointing, metrics)
- Customizing (override preflight, override validate, custom prompt)
- FAQ

### AGENTS.md (for the ralph repo itself)

How to contribute to ralph. Build conventions, test commands.

### docs/ Directory

```
docs/
├── ARCHITECTURE.md           # System design, data flow, component diagram
├── CONFIGURATION.md          # All env vars and their defaults
├── VALIDATION_GATE.md        # How the 5-step gate works, how to customize
├── PREFLIGHT_GUARDRAILS.md   # How config/ralph_preflight.sh works
├── LOOP_LIFECYCLE.md         # What happens in a single iteration
├── LANGUAGES.md              # Language-specific setup (Python, Node, Go, Rust)
├── METRICS.md                # Metrics JSONL schema and viewer usage
├── HEALTH_CHECKS.md          # What ralph_health.sh checks
├── TEMPLATES.md              # All template variables and their usage
└── FAQ.md                    # Common issues and solutions
```

## 3.2 Install Automation

### `scripts/install.sh`

```bash
#!/usr/bin/env bash
# One-command install:
#   curl -fsSL https://raw.githubusercontent.com/.../ralph/main/scripts/install.sh | bash
#
# OR:
#   git clone https://github.com/.../ralph.git ~/.ralph
#   bash ~/.ralph/scripts/install.sh

set -euo pipefail

RALPH_HOME="${RALPH_HOME:-$HOME/.ralph}"

# If not already cloned, clone the repo
if [[ ! -f "$RALPH_HOME/bin/ralph" ]]; then
    echo "Cloning ralph..."
    git clone https://github.com/gastownhall/ralph.git "$RALPH_HOME"
fi

# Symlink bin/ralph into PATH
INSTALL_DIR="/usr/local/bin"
if [[ -w "$INSTALL_DIR" ]]; then
    ln -sf "$RALPH_HOME/bin/ralph" "$INSTALL_DIR/ralph"
    echo "✓ Installed ralph → $INSTALL_DIR/ralph"
else
    echo "⚠️  Cannot write to $INSTALL_DIR. Adding to ~/.local/bin..."
    mkdir -p "$HOME/.local/bin"
    ln -sf "$RALPH_HOME/bin/ralph" "$HOME/.local/bin/ralph"
    echo "✓ Installed ralph → $HOME/.local/bin/ralph"
    echo "   Add ~/.local/bin to your PATH if not already present."
fi

echo ""
echo "Ralph Wiggum Loop Build System installed!"
echo "Run 'ralph init' to start a new project."
```

### Prerequisite checker in `init.py`

Before running init, check:
- bash 4+
- python 3.10+
- git installed
- beads (bd) installed
- at least one AI agent (kimi or pi) installed

Print clear install instructions for any missing prerequisites.

## 3.3 Project Health Dashboard

### `ralph status` command

When run inside a ralph-initialized project:

```
$ ralph status

  Project: My Cool App
  Ralph version: 1.0.0

  ── Ralph Loop ─────────────────────────────
  Status:        IDLE (no checkpoint file)
  Last activity: 2 hours ago
  Iterations today: 12
  Pass rate:      91.7% (11/12)

  ── Beads Queue ────────────────────────────
  Open:      5
  In progress: 1
  Blocked:   0
  Ready:     3

  ── Git ────────────────────────────────────
  Branch:    main
  Ahead:     2 commits
  Dirty:     no

  ── Health ─────────────────────────────────
  ✓ Metrics file recent
  ✓ Beads DB clean
  ✓ Git in sync
```

Adds `status` command to `bin/ralph`.

## 3.4 `ralph update` — Self-Update

```bash
ralph update    # git pull in RALPH_HOME
```

## 3.5 Language Support Expansion

Add validation scripts for:
- `validate_node.sh` — eslint + prettier + jest
- `validate_go.sh` — golangci-lint + gofmt + go test
- `validate_rust.sh` — clippy + rustfmt + cargo test
- `validate_other.sh` — stub that users customize

Each follows the same 5-step pattern but with language-appropriate tools.

## 3.6 Future: Ralph Server Mode

Long-running server that watches beads queue and dispatches agent iterations.
Current design is CLI-loop based. A server mode would:

- Run as a daemon (launchd/systemd)
- Watch beads queue via polling
- Dispatch agent iterations
- Expose a web dashboard (metrics, queue, health)
- Support webhook notifications (Slack, Discord)

This is Phase 4+ and out of scope for now.

## 3.7 Testing

- Unit tests for `init.py` (template rendering, auto-detection, validation)
- Shell script linting (shellcheck)
- Integration test: `ralph init` → verify all files created correctly
- Integration test: `ralph init` with each supported language
- Dogfood: use ralph to build ralph itself

## 3.8 GitHub Release

- Tag v1.0.0
- Push to GitHub (`gastownhall/ralph` or similar)
- Write release notes
- Set up the one-liner install:
  ```
  curl -fsSL https://raw.githubusercontent.com/gastownhall/ralph/main/scripts/install.sh | bash
  ```

## 3.9 Deliverables

- [x] `README.md` — complete quick-start
- [x] `docs/BUILD_SYSTEM_OVERVIEW.md` — layman-friendly explanation
- [x] `docs/ARCHITECTURE.md` — system design + mermaid diagrams
- [x] `docs/DEPLOYMENT.md` — new computer setup, high-level + step-by-step
- [x] `docs/GETTING_STARTED.md` — first project walkthrough
- [x] `docs/DAILY_USAGE.md` — must-have files, app specs, daily workflow
- [x] `docs/TROUBLESHOOTING.md` — failure scenarios, monitoring, cleanup, restart
- [x] `docs/TICKET_MANAGEMENT.md` — naming rules, beads workflow, monitoring
- [x] `docs/CONFIGURATION.md` — all env vars and defaults
- [x] `docs/FAQ.md` — common questions
- [x] `docs/html/index.html` — single-page HTML docs with dark theme + Mermaid diagrams
- [x] `scripts/install.sh` — one-liner installer
- [x] `bin/ralph status` — project health command
- [ ] `bin/ralph update` — self-update (deferred: trivial git-pull wrapper)
- [ ] `core/validate_node.sh` (deferred: Phase 4+)
- [ ] `core/validate_go.sh` (deferred: Phase 4+)
- [ ] `core/validate_rust.sh` (deferred: Phase 4+)
- [ ] `core/validate_other.sh` (deferred: Phase 4+)
- [ ] Shellcheck on all `.sh` files (deferred: requires shellcheck install)
- [ ] Tests for `init.py` (deferred)
- [ ] Dogfood: ralph builds ralph (deferred)
- [x] GitHub push to samdharma/Ralph_loop.git
