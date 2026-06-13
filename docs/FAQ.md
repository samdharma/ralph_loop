# FAQ — Frequently Asked Questions v1.2

**Revision**: 2026-06-13 — Updated for 4-stage pipeline

---

## 4-Stage Pipeline

### What is the 4-stage pipeline?

A structured workflow that splits each ticket into 4 independent sessions:

```
DESIGN → TEST → IMPLEMENT → VERIFY
```

| Stage | Command | What happens |
|-------|---------|-------------|
| DESIGN | `ralph design` | Architect plans the solution |
| TEST | `ralph test` | QA writes functional tests from the spec (before code exists) |
| IMPLEMENT | `ralph implement` | Developer writes code to pass tests + unit tests |
| VERIFY | `ralph verify` | Gatekeeper validates everything and closes the ticket |

### Why 4 stages instead of 3?

The old 3-stage pipeline had the implement session writing its own functional
tests. The AI was "marking its own homework" — tests verified the implementation,
not the spec. The new TEST stage writes tests from the design spec **before any
code exists**, creating true independent verification.

### Can I still use the old 3-stage or all-in-one loop?

Yes. `ralph loop` and `ralph daemon` still work as before. The 4-stage pipeline
is an additional workflow, not a replacement.

### Do I have to run all 4 stages for every ticket?

For critical features — yes, strongly recommended. For trivial changes (typo
fixes, doc updates), you can skip directly to `ralph loop --ticket=<id>` or
use the continuous daemon.

---

## General

### What is Ralph?

Ralph Wiggum Loop is an **AI-agent-powered continuous build system**. It reads your
ticket queue (beads), feeds tickets to an AI coding agent (kimi/pi), validates the
output, and commits it — all in a loop. You write the tickets; Ralph builds the code.

### Is this a CI/CD system?

No. Ralph is a **development-time** tool, not a CI/CD pipeline. It runs on your
development machine, not in a CI server. Think of it as an autonomous pair programmer
that works through your ticket backlog.

### Can I use Ralph without beads?

No. Ralph depends on beads (`bd`) for ticket management. The loop reads `bd ready`
to find work, `bd show` for ticket details, and `bd update` to update status.

### Can I use a different AI agent?

Currently supports `kimi` and `pi`. The agent must support a non-interactive
`--print` mode that accepts a prompt via `-p`. To add another agent, you'd modify
`ralph_loop.sh` (lines ~240-250) where the agent is invoked.

### Does Ralph work on Windows?

Not directly. Ralph is bash-based and assumes a Unix-like environment (macOS/Linux).
On Windows, use WSL2 (Windows Subsystem for Linux).

---

## Setup

### `ralph` command not found after install

```bash
# Check if symlink exists
ls -la /usr/local/bin/ralph ~/.local/bin/ralph

# If not, re-run installer
bash ~/.ralph/scripts/install.sh

# Check PATH
echo $PATH | tr ':' '\n'

# Source your profile
source ~/.zshrc  # or ~/.bashrc
```

### What if I already have a project?

```bash
# Initialize Ralph into an existing project
cd my-existing-project
ralph init
# Choose the same directory as the project root
```

Ralph will add its files alongside your existing code. It won't overwrite
existing files unless you confirm.

### Do I need a Python virtual environment?

Only if your project uses Python. The validation gate (`ralph_validate.sh`) auto-detects
`.venv` and activates it. If you're using Node or Go, no venv is needed.

---

## Usage

### How many tickets can Ralph handle?

Ralph processes one ticket per iteration (one agent invocation). A typical
iteration takes 5-30 minutes depending on task complexity and agent speed.
In a day, Ralph can process 10-30 tickets.

### Can I run Ralph on multiple projects at once?

Yes. Each project has its own PID file and checkpoint. Just run the daemon
in each project directory:

```bash
cd ~/Dev/project-a && ralph daemon
cd ~/Dev/project-b && ralph daemon
```

### What happens if my computer sleeps?

The agent process pauses. When the computer wakes, the agent continues.
If the agent times out (depends on the agent's own timeout), the checkpoint
will be retained and the loop will resume from the checkpoint on the next
iteration.

### Can I use Ralph in a team?

Ralph is designed for solo use with a shared git remote. One team member
runs Ralph locally. Others pull the commits. Multiple people running Ralph
on the same project will conflict — use branch isolation if needed.

### How do I handle secrets?

Secrets go in `.env` (never committed). Ralph's `.gitignore` excludes `.env`.
Your preflight guardrail can check for `.env` existence:

```bash
if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
    SKIP_REASON="env_file_missing"
fi
```

---

## Tickets

### Why are my tickets being skipped?

Check the preflight output in `logs/ralph_loop.log`:

```
[RALPH] Task proj.1.1 skipped — BLOCKED: some_reason
```

Then check `config/ralph_preflight.sh` to understand why. Common reasons:
- Ticket has `meta-grouping` label (epic/feature containers are skipped)
- Ticket type is `epic` or `feature`
- Custom guardrail rule blocking it

### How do I create a new phase?

```bash
# 1. Create the feature (container)
bd new "Phase 2: API Layer" --type feature --labels "phase-2,meta-grouping"

# 2. Create tasks
bd new "P2: Implement REST endpoints" --type task --labels "phase-2"
bd new "P2: Add request validation" --type task --labels "phase-2"
bd new "[EXIT] P2: API integration tests" --type task --labels "exit,phase-2"

# 3. Set phase gating (P2.1 depends on P1's EXIT ticket)
bd dep add <p2-task1-id> <p1-exit-id>

# 4. Set EXIT dependencies
bd dep add <p2-exit-id> <p2-task1-id>
bd dep add <p2-exit-id> <p2-task2-id>
```

### Should tickets be small or large?

**Small.** Each ticket should be completable in a single agent iteration
(5-30 minutes). If a ticket is too large:
- The agent will run out of context or steps
- Validation will likely fail
- The checkpoint will persist and the ticket will cycle

If you find a ticket cycling, break it into two smaller tickets.

---

## Troubleshooting

### Ralph keeps failing on the same ticket

1. Check what's failing: `ralph validate --tier=targeted`
2. Fix manually if it's a lint/format issue
3. If the task is too complex, break it up
4. Block the ticket and move on: `bd update <id> --status blocked`

### The loop stopped and won't restart

```bash
# Clean up stale state
rm -f .ralph_loop.pid .ralph_checkpoint.json

# Verify git is clean
git status

# Restart
ralph daemon
```

### How do I see what Ralph has been doing?

```bash
# Recent commits
git log --oneline -20

# Loop log
tail -100 logs/ralph_loop.log

# Metrics dashboard
ralph metrics

# Project status
ralph status
```

---

## Customization

### Can I change the validation tools?

Yes. Set `RALPH_LINT_TOOLS`:

```bash
# Use ruff instead of flake8
export RALPH_LINT_TOOLS="black isort ruff mypy"

# Minimal: just tests
export RALPH_LINT_TOOLS=""
```

### Can I add custom preflight rules?

Edit `config/ralph_preflight.sh`. The `LABELS` and `CAND_TYPE` variables are
available. Set `SKIP_REASON` to block a ticket. See `GETTING_STARTED.md` for
examples.

### Can I use a custom prompt?

Point `RALPH_PROMPT_BASE` to your custom file:

```bash
export RALPH_PROMPT_BASE="docs/agent/my_custom_prompt.md"
```

Or just edit `docs/agent/PROMPT.md` directly — the generated one is yours to customize.

### Can I run tests without the full validation gate?

```bash
# Just unit tests
pytest tests/unit/ -q --tb=short

# Just lint
black --check src/
```
