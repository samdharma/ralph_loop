# Ralph Wiggum Build System — Layman's Overview

> *What is this thing, and why would I use it?*

---

## The Problem Ralph Solves

You're building software. You've broken it into tickets (tasks). You use an AI coding agent
to implement each task. The cycle looks like this:

```
1. Pick a ticket
2. Figure out what it needs
3. Open your AI agent, paste context, ask it to implement
4. Wait for it to finish
5. Run tests, check formatting, fix what broke
6. Commit the result
7. Go back to step 1
```

This is tedious. You're the **orchestrator** — the human glue between tickets and agents.
Ralph replaces you as the orchestrator.

---

## What Ralph Is

Ralph is an **automatic ticket-to-code pipeline**. Think of it like a conveyor belt:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│              │     │              │     │              │
│  Your Ticket │ ──→ │ Ralph picks  │ ──→ │  AI Agent    │
│  Queue       │     │  the next    │     │  implements  │
│  (beads)     │     │  ready task  │     │  the task    │
│              │     │              │     │              │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                    ┌──────────────┐               │
                    │              │               │
                    │  Commit &    │ ←─────────────┘
                    │  Repeat      │    Tests pass?
                    │              │
                    └──────────────┘
```

**You write the tickets. Ralph builds the code.**

---

## A Day in the Life

### Without Ralph

1. Morning: open your laptop, figure out what to work on
2. Pick a ticket, read the description, read reference docs
3. Open kimi/pi, paste 500 lines of context, write a prompt
4. Wait 10-20 minutes for the agent to finish
5. Run tests manually, fix lint errors, re-run
6. `git add`, `git commit`, `bd update`
7. Repeat steps 2-6 for the next ticket
8. End of day: 3-4 tickets done

### With Ralph

1. Morning: `bash scripts/ralph/run_ralph_loop.sh`
2. Go make coffee, attend meetings, work on design
3. Check `git log` — 6-8 tickets committed
4. End of day: `ralph status` to see what happened

---

## What Ralph Does NOT Do

- ❌ Ralph does **not** write your tickets — you do that in beads
- ❌ Ralph does **not** design your architecture — you define that in `AGENTS.md`
- ❌ Ralph does **not** replace you as the developer — it replaces the *mechanical* steps
- ❌ Ralph does **not** run in production — it's a *development* tool

---

## Key Concepts (in Plain English)

### The Loop

Ralph runs in a loop. Each iteration:

| Step | What Happens | Why |
|------|-------------|-----|
| **1. Pick** | Queries beads for the next unblocked ticket | No manual triage |
| **2. Filter** | Runs your preflight rules (e.g., "skip tickets labeled `needs-gpu` if no GPU") | Safety first |
| **3. Prompt** | Builds a context-rich prompt from your AGENTS.md, the ticket, and reference docs | Agent has full context |
| **4. Build** | Hands the prompt to kimi or pi. The agent implements the task. | Actual coding |
| **5. Validate** | Runs tests + lint + type-check on changed files only | Quality gate |
| **6. Commit/Repeat** | If clean, commits. If dirty, checkpoints and moves on. | Progress tracking |

### Checkpointing

If an agent iteration crashes or the agent can't finish, Ralph saves a checkpoint file
and rolls back the worktree on the next run. No half-finished code left behind.

### Preflight Guardrails

You control which tickets run when. Example rules:
- "Don't run `e2e` tickets between 9am-5pm" (market hours)
- "Don't run `deploy` tickets unless the `deploy` label has a specific tag"
- "Skip all tickets if `.env` is missing"

These live in `config/ralph_preflight.sh` — a simple bash script you edit.

### Validation Gate

After every agent iteration, Ralph runs:
1. **Tests** — only the test files affected by the change (via `TEST_MAP.yaml`)
2. **Formatter** — `black`, `isort` (only on changed files)
3. **Linter** — `flake8`, `mypy` (only on changed files)

All 3 must pass. If any fail, the checkpoint stays and the next iteration picks up where
the last one left off.

---

## Who Should Use Ralph

| You are... | Ralph is for you if... |
|------------|----------------------|
| A solo developer | You want to multiply your output by parallelizing with AI |
| A team lead | You want a consistent build pipeline that runs 24/7 |
| An open-source maintainer | You have a backlog of well-defined tickets |
| A startup founder | You need to ship features fast with a small team |

---

## When NOT to Use Ralph

- If your tickets are vague ("fix the thing")
- If you don't use beads for issue tracking
- If you don't have tests (the validation gate needs tests to work)
- If your project is in exploration/prototype mode (tickets change too fast)

---

## Next Steps

1. [DEPLOYMENT.md](DEPLOYMENT.md) — Install Ralph on your computer
2. [GETTING_STARTED.md](GETTING_STARTED.md) — Create your first Ralph project
3. [DAILY_USAGE.md](DAILY_USAGE.md) — Day-to-day workflow
