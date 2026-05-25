# Phase 2 — Build `ralph init` Command

**Goal**: A single `ralph init` command that interactively asks the user a set of
Q&A prompts, then initializes a project directory with:
- Git initialized
- Beads initialized (`bd init`)
- Ralph core scripts copied in
- All templates rendered with user's answers
- Language-specific validation gate generated
- `.gitignore` populated with ralph entries

**Status**: ✅ COMPLETE

---

## 2.1 CLI Entry Point — `bin/ralph`

A minimal bash wrapper that dispatches to subcommands:

```bash
#!/usr/bin/env bash
# ralph — Ralph Wiggum Loop Build System CLI

case "${1:-}" in
    init)
        shift
        python3 "$RALPH_HOME/init.py" "$@"
        ;;
    version|--version|-v)
        echo "ralph v1.0.0"
        ;;
    help|--help|-h|"")
        cat <<EOF
Ralph Wiggum Loop Build System

Commands:
  ralph init     Initialize a new project with the Ralph build system
  ralph version  Show version
  ralph help     Show this help

Project commands (inside an initialized project):
  bash scripts/ralph/ralph_loop.sh     Run the agentic build loop
  bash scripts/ralph/run_ralph_loop.sh Run as background daemon
  bash scripts/ralph/ralph_validate.sh Run validation gate
  bash scripts/ralph/ralph_health.sh   Check loop health
EOF
        ;;
    *)
        echo "ralph: unknown command '${1}'"
        echo "Run 'ralph help' for usage."
        exit 1
        ;;
esac
```

## 2.2 Init Wizard — `init.py`

### Flow

```
$ ralph init

  ██████╗  █████╗ ██╗     ██████╗ ██╗  ██╗
  ██╔══██╗██╔══██╗██║     ██╔══██╗██║  ██║
  ██████╔╝███████║██║     ██████╔╝███████║
  ██╔══██╗██╔══██║██║     ██╔═══╝ ██╔══██║
  ██║  ██║██║  ██║███████╗██║     ██║  ██║
  ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝

  Ralph Wiggum Loop Build System — Project Initializer

  Project name: My Cool App
  Project directory [/Users/sam.dharma/Dev/my-cool-app]:
  Primary language [python]:
    Available: python, node, go, rust, other
  AI agent [auto-detect]:
    1) kimi — Kimi CLI (available)
    2) pi   — Pi Coding Agent (available)
    3) both — Auto-detect best available
  Test framework [pytest]:
  Lint / format tools [black isort flake8 mypy]:
  Brief project description:
    > A web scraper that collects financial data

  Summary:
    Project:       My Cool App
    Directory:     /Users/sam.dharma/Dev/my-cool-app
    Package:       my_cool_app
    Language:      python
    AI Agent:      auto-detect (kimi preferred)
    Test runner:   pytest
    Lint tools:    black isort flake8 mypy

  Proceed? [Y/n]: y

  ✓ Created project directory
  ✓ Initialized git repository
  ✓ Initialized beads (bd init)
  ✓ Installed Ralph core scripts → scripts/ralph/
  ✓ Generated AGENTS.md
  ✓ Generated docs/agent/PROMPT.md
  ✓ Generated docs/agent/PROGRESS.md
  ✓ Generated docs/agent/prompts/
  ✓ Generated config/ralph_preflight.sh
  ✓ Generated config/TEST_MAP.yaml
  ✓ Generated .gitignore

  ✓ Project initialized!

  Quick start:
    cd /Users/sam.dharma/Dev/my-cool-app
    bash scripts/ralph/ralph_loop.sh --agent=kimi

  Next steps:
    1. Review and customize AGENTS.md
    2. Review docs/agent/PROMPT.md for project-specific context
    3. Create your first ticket: bd new "My first task"
    4. Start the loop: bash scripts/ralph/run_ralph_loop.sh
```

### Questions Asked

| # | Question | Default | Type |
|---|----------|---------|------|
| 1 | `PROJECT_NAME` | — | str (required) |
| 2 | `PROJECT_DIR` | `./<slug>` | path |
| 3 | `PROJECT_LANGUAGE` | `python` | choice: python, node, go, rust, other |
| 4 | `AGENT_CHOICE` | `auto` | choice: kimi, pi, both, auto |
| 5 | `TEST_FRAMEWORK` | auto-based-on-language | str |
| 6 | `LINT_TOOLS` | auto-based-on-language | str list |
| 7 | `PROJECT_DESCRIPTION` | — | str (optional) |

### Auto-detection logic

- **Agent**: Check `which kimi` and `which pi`. Offer available ones. Default to first available.
- **Tests**: Python→pytest, Node→jest, Go→go test, Rust→cargo test
- **Lint**: Python→"black isort flake8 mypy", Node→"eslint prettier", Go→"golangci-lint", Rust→"clippy rustfmt"

### What the init command does

```
1. Validate inputs
2. Create PROJECT_DIR if it doesn't exist
3. git init
4. bd init
5. Create directory structure:
   - scripts/ralph/
   - config/
   - docs/agent/prompts/
   - logs/
   - tests/ (or __tests__, etc.)
   - src/<package>/
6. Copy core scripts from ralph/core/ → scripts/ralph/
   (with RALPH_CORE_DIR pointing back to ralph install)
7. Render and write all templates:
   - AGENTS.md
   - docs/agent/PROMPT.md
   - docs/agent/PROGRESS.md
   - docs/agent/prompts/*.md
   - config/ralph_preflight.sh
   - config/TEST_MAP.yaml
   - .gitignore
8. Generate language-specific validation script:
   - scripts/ralph/ralph_validate.sh (Python version)
   - or pass-through to ralph/core/validate_python.sh etc.
9. Print summary and quick-start instructions
```

## 2.3 Template Rendering

Simple string replacement. Each `.j2` file has `{{ VAR }}` placeholders.

Implementation approach: Read `.j2` file, run through Python `string.Template` or simple
`str.replace()`. No Jinja2 dependency needed — these are simple key-value replacements.

## 2.4 Language-Specific Validation Scripts

### Python (`validate_python.sh`)

The current `ralph_validate.sh` from SAM Trader, generalized:
- `RALPH_PYTHON_CMD` for python binary
- `RALPH_VENV_PATH` for venv
- `RALPH_LINT_TOOLS` to control which tools run
- `RALPH_TEST_RUNNER` to allow custom pytest args

### Validation Hook Pattern

The core loop calls `scripts/ralph/ralph_validate.sh`. The init command generates this file
based on language choice. For unsupported languages, it generates a stub that the user fills in.

## 2.5 Deliverables

- [x] `PHASE_2_ROADMAP.md` — this file
- [x] `bin/ralph` — CLI entry point
- [x] `init.py` — Interactive Q&A wizard
- [x] `scripts/install.sh` — Symlink installer
- [x] Template rendering engine in `init.py`
- [x] Language-specific validation script generation
- [x] Git + Beads initialization
- [x] Core script copier
