# FAQ — Frequently Asked Questions

---

## General

### What is Ralph?

Ralph Wiggum Loop is an AI-agent-powered continuous build system. It reads your ticket queue (beads), feeds tickets to an AI coding agent (kimi or pi), validates the output, and commits — in a loop. See the [Getting Started guide](getting-started.md) for a full walkthrough.

### Is this a CI/CD system?

No. Ralph is a **development-time** tool that runs on your machine, not a CI pipeline. Think of it as an autonomous pair programmer that works through your ticket backlog.

### Does Ralph work on Windows?

Not directly. Ralph is bash-based and requires a Unix-like environment (macOS or Linux). On Windows, use WSL2.

### Can I use Ralph without beads?

No. Ralph depends on beads (`bd`) for ticket management — `bd ready` to find work, `bd show` for details, `bd update` to change status.

### Can I use a different AI agent?

Currently supports `kimi` and `pi`. The agent must support a non-interactive `--print` mode that accepts a prompt via `-p`.

---

## Setup

### `ralph` command not found after install

```bash
ls -la /usr/local/bin/ralph ~/.local/bin/ralph   # check symlinks
bash ~/.ralph/scripts/install.sh                   # re-run installer
echo $PATH | tr ':' '\n'                           # check PATH
source ~/.zshrc                                     # reload profile
```

### What if I already have a project?

```bash
cd my-existing-project
ralph init
```

Ralph adds its files alongside your existing code. It won't overwrite files unless you confirm.

### Do I need a Python virtual environment?

Only if your project uses Python. The validation gate auto-detects `.venv` and activates it. Node and Go projects don't need one.

---

## Usage

### How many tickets can Ralph handle?

One ticket per iteration (one agent invocation). A typical iteration takes 5–30 minutes. In a day, 10–30 tickets.

### Can I run Ralph on multiple projects at once?

Yes. Each project has its own PID file and checkpoint:

```bash
cd ~/dev/project-a && ralph daemon
cd ~/dev/project-b && ralph daemon
```

### What happens if my computer sleeps?

The agent process pauses. When the computer wakes, the agent continues. If the agent times out, the checkpoint is retained and the loop resumes on the next iteration.

### Can I use Ralph in a team?

Ralph is designed for solo use with a shared git remote. One team member runs Ralph locally; others pull the commits. Multiple people running Ralph on the same project will conflict — use branch isolation.

### How do I handle secrets?

Secrets go in `.env` (never committed). Ralph's `.gitignore` excludes it. Your preflight guardrail can enforce its existence:

```bash
if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
    SKIP_REASON="env_file_missing"
fi
```

---

## Pipeline

### What is the 4-stage pipeline?

A structured workflow splitting each ticket into 4 independent sessions: DESIGN → TEST → IMPLEMENT → VERIFY. The TEST stage writes functional tests from the design spec **before any code exists**, creating true independent verification. See [Daily Usage](daily-usage.md) for details.

### Do I have to use all 4 stages for every ticket?

For critical features — yes, strongly recommended. For trivial changes (typos, docs), skip directly to `ralph loop --ticket=<id>` or use the continuous daemon.

### Can I still use the all-in-one loop?

Yes. `ralph loop` and `ralph daemon` still work. The 4-stage pipeline is an additional, higher-quality workflow.

---

## Tickets

### Why are my tickets being skipped?

Check the loop log for `BLOCKED` messages, then review `config/ralph_preflight.sh`. Common reasons: ticket has `meta-grouping` label (epics/features are containers), or a custom guardrail rule is blocking it. See [Ticket Management](ticket-management.md).

### How do I create a new phase?

See the "Creating a New Phase" pattern in [Ticket Management](ticket-management.md#creating-a-new-phase).

### Should tickets be small or large?

**Small.** Each ticket should be completable in a single agent iteration (5–30 minutes). If a ticket cycles repeatedly, break it into two smaller tickets.

---

## Customization

### Can I change the validation tools?

Yes. Set `RALPH_LINT_TOOLS`:

```bash
export RALPH_LINT_TOOLS="black isort ruff mypy"   # use ruff instead of flake8
export RALPH_LINT_TOOLS=""                          # skip lint, tests only
```

### Can I add custom preflight rules?

Edit `config/ralph_preflight.sh`. The `LABELS` and `CAND_TYPE` variables are available. Set `SKIP_REASON` to block a ticket.

### Can I use a custom agent prompt?

Point `RALPH_PROMPT_BASE` to your file, or just edit `docs/agent/PROMPT.md` directly — the generated one is yours to customize.

---

## Troubleshooting

For detailed failure scenarios, recovery procedures, and cleanup, see the [Troubleshooting section](daily-usage.md#troubleshooting) in the Daily Usage guide.

Quick fixes for common issues:

```bash
# Ralph won't restart
rm -f .ralph_loop.pid .ralph_checkpoint.json

# See what Ralph has been doing
git log --oneline -20
tail -100 logs/ralph_loop.log
ralph status

# Full cleanup and restart
kill $(cat .ralph_loop.pid) 2>/dev/null || true
rm -f .ralph_loop.pid .ralph_checkpoint.json
git status          # should be clean
ralph daemon
```
