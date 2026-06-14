# Ralph v3 — Product Requirements Document

> Working draft. Defines the revamped system. Updated as brainstorming progresses.

---

## 0. Prerequisites

### 0.1 Required Tools (Per Machine)

Every machine that runs Ralph needs these installed:

| Tool | Version | Install | Purpose |
|------|---------|---------|---------|
| **git** | 2.30+ | `brew install git` / `apt install git` / built-in on macOS | Version control, clone, push, pull |
| **gh** (GitHub CLI) | 2.0+ | `brew install gh` / `apt install gh` / `winget install gh` | Issue read/write, label management |
| **python3** | 3.10+ | `brew install python` / `apt install python3` | Core orchestrator language. All Ralph engine code is Python. |
| **pi** or **kimi** | latest | `npm install -g pi-coding-agent` or `npm install -g kimi-cli` | AI agent for code generation |
| **pi-subagent** (pi extension) | latest | `pi extension install @mjakl/pi-subagent` | Sub-agent support for Mode A/B isolation (Phase 3) |

**Implementation language:** All Ralph v3 engine code is **Python 3.10+**. No bash beyond the CLI entry point (`bin/ralph`) and the install script. The v2 mistake of 1000+ lines of bash is not repeated.

### 0.2 GitHub CLI Authentication (One-Time Per Machine)

```bash
# Must be authenticated to read/write issues
ga auth login

# Verify
ga auth status
gh issue list --repo samdharma/my-project --limit 1  # smoke test
```

### 0.3 Ralph Global Install (One-Time Per Machine)

```bash
git clone https://github.com/samdharma/Ralph_loop.git ~/.ralph
cd ~/.ralph && git checkout ralph-v3
bash ~/.ralph/scripts/install.sh
source ~/.zshrc   # or ~/.bashrc
ralph version     # verify: ralph v3.0.0
```

---

### 0.4 GitHub Project Setup (Per Project)

Before Ralph can build a project, the GitHub repo must have:

### Labels

Create these labels in the repo (one-time, or automatable via `ralph init`):

```bash
# Type labels
ga label create "type:task" --color 0E8A16 --repo owner/repo
ga label create "type:bug" --color D73A4A --repo owner/repo
ga label create "type:feature" --color 0075CA --repo owner/repo
ga label create "type:epic" --color 3F2D7E --repo owner/repo
ga label create "type:exit" --color FBCA04 --repo owner/repo

# Status labels (Ralph manages these)
ga label create "status:ready" --color 0E8A16 --repo owner/repo
ga label create "status:design" --color 1D76DB --repo owner/repo
ga label create "status:build" --color 0052CC --repo owner/repo
ga label create "status:verify" --color 5319E7 --repo owner/repo
ga label create "status:review" --color D4C5F9 --repo owner/repo
ga label create "status:blocked" --color B60205 --repo owner/repo

# Phase labels
ga label create "phase:1" --color F9D0C4 --repo owner/repo
ga label create "phase:2" --color FEF2C0 --repo owner/repo
ga label create "phase:3" --color C2E0C6 --repo owner/repo

# Optional priority labels
ga label create "priority:1" --color D93F0B --repo owner/repo
ga label create "priority:2" --color E99695 --repo owner/repo
ga label create "priority:3" --color F9D0C4 --repo owner/repo
```

### Kanban Board (GitHub Projects)

Create a GitHub Project with the **Kanban** template. Columns map to status labels:

| Column | Maps To Label |
|--------|---------------|
| **Backlog** | No `status:*` label (or `type:epic`, `type:feature`) |
| **Ready** | `status:ready` |
| **In Design** | `status:design` |
| **In Build** | `status:build` |
| **In Verify** | `status:verify` |
| **Review** | `status:review` |
| **Blocked** | `status:blocked` |
| **Done** | Closed |

Ralph moves issues between columns automatically by updating labels. The human watches the board — no CLI tailing.

### Issue Template (Optional)

A GitHub Issue template to encourage consistent ticket formatting for Ralph:

```markdown
### Description
<!-- What needs to be built or fixed -->

### Acceptance Criteria
<!-- Checkboxes that must all be ticked for the issue to be done -->
- [ ] Criterion 1
- [ ] Criterion 2

### Reference Docs
<!-- Optional: BUILD_<feature>.md files to include in agent context -->
Reference: docs/reference/BUILD_order_book.md

### Dependencies
<!-- Optional: other issues this depends on -->
Depends on: #42
```

### Cloning a Ralph Project on a New Machine

```bash
git clone https://github.com/owner/repo.git
cd repo
ralph setup          # checks gh auth, git remote, creates local dirs
ralph daemon         # start building
```

No `bd init`. No `dolt pull`. No local database. Just git clone + ralph setup.

---

## 1. Context & Rationale

### What Went Wrong With v2

Ralph v2 was a "decoupling" effort that produced more coupling:

| Problem | Details |
|---------|---------|
| **Two overlapping engines** | `ralph_loop.sh` (all-in-one loop) and `ralph_build.sh` (orchestrator) share ~70% of their logic — arg parsing, beads interaction, prompt assembly, agent invocation — but are separate 500-line bash scripts. `build.sh` just calls `loop.sh --session=X` in a for-loop. |
| **Bash spaghetti** | State management via `python3 -c "import json..."` one-liners. Checkpoint/resume duplicated but incompatible between the two engines. Two different completion signals (`RALPH_ITERATION_COMPLETE` vs `RALPH_SESSION_COMPLETE`). |
| **Beads is heavy** | Requires `dolt` database. `bd` upgrades break worktrees. Sqlite vs JSONL syncing issues with older reports. Cannot install `bd` on all target machines. Beads is the deepest coupling surface in the entire system. |
| **Zero observability** | The 4-stage pipeline runs silently. You don't know which stage a ticket is in without tailing logs. Status is buried in JSON state files. |
| **16 CLI subcommands, 2 real engines** | The CLI is a facade. `design`, `test`, `implement`, `verify`, `loop`, `daemon`, `build` — all route to the same two scripts with flag permutations. |

### Principles for v3

1. **Remove beads entirely.** Tickets live in GitHub Issues. Code lives in git. No local DB.
2. **Clean core first, then enhance.** Define minimal, well-bounded interfaces before adding sub-agents.
3. **Observable by default.** Ticket status is a GitHub label visible on the Kanban board. Every state transition is a label change.
4. **GitHub is source of truth.** One remote, many local repos. Push/pull is the sync mechanism.
5. **Simplify the pipeline.** 3 stages with sub-agents, not 4 stages with flag-hacks.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  GitHub (Remote)                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Issues   │  │ Repo (git)   │  │ Projects      │  │
│  │ (tickets)│  │ (code+docs)  │  │ (Kanban board)│  │
│  └────┬─────┘  └──────┬───────┘  └───────┬───────┘  │
└───────┼───────────────┼──────────────────┼──────────┘
        │               │                  │
   gh issue list   git clone/pull     Human visualization
   gh issue edit   git add/commit     (read-only for Ralph)
        │           git push
        │               │
┌───────┴───────────────┴──────────────────────────────┐
│                   Local Machine                       │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │              Ralph CLI (bin/ralph)           │     │
│  │  init | daemon | status | validate | report │     │
│  └─────────────────┬───────────────────────────┘     │
│                    │                                  │
│  ┌─────────────────┴───────────────────────────┐     │
│  │         Ralph Pipeline Engine               │     │
│  │                                             │     │
│  │  Fetch Tickets  →  Pipeline Loop  →  Commit │     │
│  │  (gh issue list)   (3 stages)      (git)    │     │
│  └─────────────────┬───────────────────────────┘     │
│                    │                                  │
│  ┌─────────────────┴───────────────────────────┐     │
│  │           Agent Invocation Layer             │     │
│  │                                             │     │
│  │  Parent Agent (pi/kimi)                     │     │
│  │    └─ Sub-agents (pi-subagent / kimi)       │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │           Validation Gate                    │     │
│  │  pytest (tiered) + lint + type-check         │     │
│  └─────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────┘
```

### Key Dependencies

| Dependency | Role | Notes |
|------------|------|-------|
| **git** | Code versioning, push/pull sync | Assumed always available |
| **gh** (GitHub CLI) | Issue read/write, label management | Assumed network available |
| **pi / kimi** | AI agent + sub-agents | At least one required |
| **pytest** (or project test runner) | Validation gate | Project-specific |

**Removed from v2:** `bd` (beads), `dolt`, `dolt status`, `.beads/` directory, embedded Dolt DB.

---

## 3. Ticket Management

### GitHub Issues as the Ticket Store

All tickets are GitHub Issues. No local database. No sync problems.

### Label Convention

| Label | Purpose | Set by |
|-------|---------|--------|
| `type:task` | Work ticket | Human (during creation) |
| `type:bug` | Bug fix | Human |
| `type:feature` | Feature container | Human |
| `type:epic` | Epic container | Human |
| `type:exit` | Exit / integration ticket | Human |
| `phase:N` | Phase group (e.g., `phase:1`) | Human |
| `status:ready` | Ready to be worked on | Human OR Pipeline |
| `status:design` | In design stage | Pipeline |
| `status:build` | In build stage (test + implement) | Pipeline |
| `status:verify` | In verify stage | Pipeline |
| `status:review` | Awaiting human review | Pipeline |
| `status:blocked` | Cannot proceed | Human OR Pipeline |
| `priority:N` | Priority 1, 2, 3 (optional ordering) | Human |

### How Ralph Queries Tickets

```bash
# Get all ready, unblocked issues
gh issue list \
  --label "status:ready" \
  --state open \
  --json number,title,labels,body \
  --limit 50
```

No local DB. No `dolt pull`. No `bd ready`.

### How Ralph Updates Ticket Status

```bash
# Move to in-progress (claims the ticket)
gh issue edit $NUMBER --add-label "status:in-progress" --remove-label "status:ready"

# Move through pipeline stages
gh issue edit $NUMBER --add-label "status:design" --remove-label "status:in-progress"
gh issue edit $NUMBER --add-label "status:build" --remove-label "status:design"
gh issue edit $NUMBER --add-label "status:verify" --remove-label "status:build"

# Hand off to human
gh issue edit $NUMBER --add-label "status:review" --remove-label "status:verify"
```

Every state transition is observable on the GitHub Projects Kanban board in real time.

### Ticket Selection Order

Ralph selects the **open `status:ready` issue with the smallest number**. Example: if issues #31, #45, and #97 are all `status:ready`, Ralph picks #31. This is deterministic, predictable, and natural.

```bash
gh issue list --label "status:ready" --state open --json number \
  --jq 'min_by(.number).number'
```

### Dependencies Between Issues

A parenthetical `Depends on: #42` in the issue body. Ralph checks:

```bash
# If issue has "Depends on: #42", check if #42 is closed
gh issue view 42 --json state --jq '.state'
```

If any dependency is still open, Ralph skips the issue and optionally marks it `status:blocked`.

### EXIT Tickets

An exit ticket is simply a `type:exit` issue whose body lists acceptance criteria and integration tests. It depends on all `type:task` issues for its phase. Ralph processes it last.

---

## 4. The 3-Stage Pipeline

```
Issue #31 (status:ready)
    │
    ▼
┌──────────┐
│ STAGE 1  │  DESIGN
│ DESIGN   │  Parent Agent, Mode B (full context)
│          │  → Reads ticket + codebase
│          │  → Produces design spec in PROGRESS.md
│          │  → Updates label: status:design
└────┬─────┘
     │
     ▼
┌──────────────────────────┐
│ STAGE 2                  │  BUILD
│ BUILD                    │
│                          │
│  ┌─────────┐  ┌─────────┐│
│  │TEST     │  │IMPLEMENT││
│  │Sub-agt  │  │Sub-agt  ││
│  │Mode A   │  │Mode B   ││
│  │(no ctxt)│  │(full    ││
│  │         │  │ context)││
│  │Writes   │  │Writes   ││
│  │tests    │  │code +   ││
│  │from spec│  │unit test││
│  └─────────┘  └─────────┘│
│                          │
│  Updates label: status:build
└────────────┬─────────────┘
             │
             ▼
┌──────────┐
│ STAGE 3  │  VERIFY
│ VERIFY   │  Sub-agent, Mode A (no context)
│          │  → Sees ticket + design spec + git diff only
│          │  → 5-axis review + acceptance criteria check
│          │  → Validation gate (ralph validate)
│          │  → Updates label: status:verify (during)
│          │  → On pass: status:review (handoff to human)
│          │  → On fail: status:blocked (back to human)
└──────────┘
```

### Sub-Agent Modes

| Mode | Context | Used For | Rationale |
|------|---------|----------|-----------|
| **A — Isolated** | Sub-agent gets a FRESH session. Does not inherit parent context. | TEST sub-agent, VERIFY sub-agent | Genuine independent testing. Prevents "marking your own homework." |
| **B — Sequential** | Sub-agent inherits parent context (full conversation history, codebase knowledge). | IMPLEMENT sub-agent | Developer needs to see the design spec, test files, and codebase to implement correctly. |

### Prompt Personas

| Role | Stage | Initial Prompt |
|------|-------|----------------|
| **Architect / Systems Analyst** | DESIGN (Parent) | "You are a systems architect. Read the issue, research the codebase, surface assumptions, define success criteria. Produce a design spec in PROGRESS.md. Do NOT write implementation code or tests." |
| **QA Engineer** | TEST (Sub, Mode A) | "You are a QA engineer reviewing a design spec. Write functional and system tests from the spec ONLY. Do not see or reference any implementation code. Every acceptance criterion must map to at least one test. Tests SHOULD FAIL — there is no implementation yet." |
| **Developer** | IMPLEMENT (Sub, Mode B) | "You are a developer building to spec. The design spec and tests exist. Write minimal code to make the tests pass. Write unit tests for internal logic. Do not modify existing tests (except compilation fixes). Commit each working slice." |
| **Independent Reviewer** | VERIFY (Sub, Mode A) | "You are an independent reviewer. You see: the original issue, the design spec, and the git diff. Do a 5-axis review (correctness, simplicity, tests, security, maintainability). Run the validation gate. Report pass/fail per acceptance criterion." |

### Stage Transition Protocol

Each stage follows a strict entry/exit contract:

```
Enter Stage:
  1. Update issue label to status:<stage>
  2. Assemble prompt for agent/sub-agent
  3. Invoke agent

Exit Stage:
  1. Agent signals completion
  2. Commit all changes: git add -A && git commit -m "[ralph] <stage>: #<issue>"
  3. Update issue label to next stage's status
  4. Log metrics event
```

---

## 5. Loop Lifecycle (Daemon Mode)

### Continuous Loop Flow

```
START (ralph daemon)
    │
    ▼
┌─────────────────────┐
│ 1. SYNC             │
│  git fetch origin   │
│  git merge/ff       │
│  (safety gate:      │
│   divergence = stop)│
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 2. FETCH TICKET     │
│  gh issue list      │
│  --label ready      │
│  --state open       │
│  → smallest number  │
└────────┬────────────┘
         │ no ready tickets → sleep 60s, loop
         ▼
┌─────────────────────┐
│ 3. CLAIM TICKET     │
│  gh issue edit      │
│  add: status:design │
│  remove: ready      │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 4. PIPELINE         │
│  DESIGN → BUILD →   │
│  VERIFY              │
│  (3 stages as above) │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 5. HANDOFF          │
│  Ticket marked       │
│  status:review       │
│  (if --auto-close:   │
│   close issue)      │
└────────┬────────────┘
         │
    sleep 5s, loop
```

### Signal Handling & Crash Recovery

- **SIGINT/SIGTERM:** Clear active checkpoint, mark current issue as `status:blocked` with note "interrupted", exit cleanly.
- **Crash during stage:** On restart, check for any issue marked `status:design|status:build|status:verify`. Re-enter pipeline at the appropriate stage. Git worktree check determines partial progress.
- **Power loss:** Same as crash. Checkpoint file tracks active issue + active stage + pre-stage commit SHA.

### Concurrency Guard

PID-file singleton (same as v2). Only one `ralph daemon` per project.

---

## 6. Validation Gate (unchanged from v2)

The validation gate is one part of v2 that works well. It stays largely as-is.

```
ralph validate --tier=<smoke|targeted|integration|full>
```

| Tier | Scope | Use |
|------|-------|-----|
| `smoke` | Unit tests, fail-fast | Fastest feedback |
| `targeted` | Affected tests only (via TEST_MAP.yaml + git diff) | Default in loop |
| `integration` | Integration marker tests | Pre-merge |
| `full` | All tests except e2e/perf | VERIFY stage |

Lint tools run on modified files only. e2e and performance tests are blocked in the loop (override: `RALPH_ALLOW_E2E=1`).

---

## 7. CLI Surface (Simplified)

| Command | Purpose | v2 Equivalent |
|---------|---------|---------------|
| `ralph init` | Scaffold new project | `ralph init` |
| `ralph setup` | Post-clone: check gh, git, dependencies, create local dirs | `ralph setup` (new) |

**`ralph setup` details:**

```
ralph setup must:
  1. Verify gh is authenticated (gh auth status)
  2. Verify git remote exists (git remote -v)
  3. Create local directories: logs/, .ralph/
  4. Check python3, pi/kimi, pytest are available
  5. Report missing dependencies with install instructions
  6. Exit 0 if all checks pass
```

| `ralph daemon` | Start background build loop | `ralph daemon` |
| `ralph status` | Project health dashboard | `ralph status` |
| `ralph validate` | Run validation gate | `ralph validate` |
| `ralph report` | Generate daily/weekly report | `ralph report` |

**Removed from v2 CLI:** `ralph loop` (merged into daemon), `ralph design|test|implement|verify|build` (all internal to the pipeline engine — not user-facing), `ralph health` (merged into status), `ralph sync` (automatic in daemon loop), `ralph metrics` (merged into report/status).

---

## 8. Project Scaffold (ralph init)

The init wizard generates a project with:

```
my-project/
├── .ralph/
│   └── config.toml          # Project config (no secrets)
├── config/
│   ├── ralph_preflight.sh   # Pre-flight guardrails
│   └── TEST_MAP.yaml        # Source → test mapping
├── docs/
│   └── agent/
│       ├── PROMPT.md         # Base agent prompt
│       ├── PROGRESS.md       # Agent progress log
│       └── prompts/
│           ├── design.md     # DESIGN stage prompt
│           ├── test.md       # TEST sub-agent prompt
│           ├── implement.md  # IMPLEMENT sub-agent prompt
│           ├── verify.md     # VERIFY sub-agent prompt
│           ├── feature.md    # Feature-specific guidance
│           ├── bugfix.md     # Bugfix-specific guidance
│           └── docs.md       # Documentation guidance
├── logs/
│   ├── ralph_daemon.log      # Daemon output
│   └── ralph_metrics.jsonl   # Structured metrics
├── src/
│   └── my_project/
├── tests/
│   ├── unit/
│   └── integration/
├── AGENTS.md                 # Quick reference for agents
└── .gitignore
```

**Removed from v2 scaffold:** `.beads/` directory, `bd init`, `dolt pull`, `config.toml.j2` with `[beads]` section.

---

## 9. Metrics & Observability

### Issue Status = Real-Time Progress

Because every pipeline stage updates the issue label, the GitHub Kanban board shows live progress. No need to `tail -f logs/ralph_loop.log` to know what's happening.

### Structured Metrics (ralph_metrics.jsonl)

```json
{"timestamp":"2026-06-14T10:30:00Z","event":"pipeline_start","issue":"31","agent":"pi"}
{"timestamp":"2026-06-14T10:30:05Z","event":"stage_start","issue":"31","stage":"design","agent":"pi"}
{"timestamp":"2026-06-14T10:32:10Z","event":"stage_complete","issue":"31","stage":"design"}
{"timestamp":"2026-06-14T10:32:15Z","event":"stage_start","issue":"31","stage":"build","subagent_test":"pi","subagent_implement":"pi"}
{"timestamp":"2026-06-14T10:35:00Z","event":"stage_complete","issue":"31","stage":"build"}
{"timestamp":"2026-06-14T10:35:05Z","event":"stage_start","issue":"31","stage":"verify","subagent":"pi"}
{"timestamp":"2026-06-14T10:36:00Z","event":"validation_pass","issue":"31","tier":"targeted"}
{"timestamp":"2026-06-14T10:36:05Z","event":"pipeline_complete","issue":"31","result":"review"}
```

---

## 10. Build Phase Reference Docs

In v2, `BUILD_PHASE_N.md` files under `docs/reference/` provided pre-discovered type mappings and SDK references to save the agent from re-researching APIs. These are **kept** in v3 but generalized:

- Renamed to `BUILD_<feature>.md` (e.g., `BUILD_websocket_feed.md`)
- Referenced in the issue body: `Reference: docs/reference/BUILD_websocket_feed.md`
- The DESIGN agent reads this as part of its research
- Lives in the repo, versioned alongside code
- Optional — the pipeline works without them, just slower

---

## 11. Agent Orchestrator — Summary

> This section consolidates the orchestrator design decisions from sections 4 and 5
> into a single reference for implementers.

### Orchestrator Responsibilities

The orchestrator is the pipeline engine. It is NOT a bash wrapper around an all-in-one loop — it is the core itself.

| Responsibility | How |
|---------------|-----|
| **Ticket selection** | `gh issue list --label status:ready` → pick lowest issue number |
| **Claiming** | `gh issue edit` — add `status:design`, remove `status:ready` |
| **Stage dispatch** | Invoke parent agent or sub-agent with stage-specific persona prompt |
| **State tracking** | Checkpoint file: `{ issue, stage, pre_commit_sha, started_at }` |
| **Stage commits** | `git add -A && git commit -m "[ralph] <stage>: #<issue>"` after each stage |
| **Label transitions** | `gh issue edit` at every stage boundary |
| **Crash recovery** | On restart, find any issue with `status:design|status:build|status:verify`, resume at that stage |
| **Handoff** | After VERIFY passes → mark `status:review`. After VERIFY fails → mark `status:blocked`. |

### The 3 Stages (Recap)

| Stage | Agent | Mode | Input | Output |
|-------|-------|------|-------|--------|
| **DESIGN** | Parent agent | B (full context) | Issue body + codebase + BUILD_*.md reference docs | Design spec in PROGRESS.md |
| **BUILD** | 2 sub-agents | TEST: Mode A (isolated), IMPLEMENT: Mode B (sequential) | Design spec | Tests that fail + code that passes + unit tests |
| **VERIFY** | Sub-agent | A (isolated) | Issue + design spec + git diff | Pass/fail report + acceptance criteria checklist |

### Sub-Agent Invocation Model

```
┌─────────────────────────────────────────────┐
│            Parent Agent (DESIGN)             │
│  Full codebase context. Produces spec.       │
└──────────────────┬──────────────────────────┘
                   │ spec (PROGRESS.md)
     ┌─────────────┴─────────────┐
     ▼                           ▼
┌──────────────┐         ┌──────────────┐
│ TEST Sub-Agt │         │IMPL Sub-Agt  │
│   Mode A     │         │   Mode B     │
│              │         │              │
│ Fresh session│         │ Inherits     │
│ Sees: spec   │         │ parent ctx   │
│ only         │         │ Sees: spec + │
│              │         │ codebase +   │
│ Writes: test │         │ test files   │
│ files        │         │              │
│              │         │ Writes: code │
│              │         │ + unit tests │
└──────┬───────┘         └──────┬───────┘
       │                        │
       └──────────┬─────────────┘
                  │ code + tests committed
                  ▼
         ┌──────────────┐
         │VERIFY Sub-Agt│
         │   Mode A     │
         │              │
         │ Fresh session│
         │ Sees: issue  │
         │ + spec + diff│
         │              │
         │ 5-axis review│
         │ + validation │
         │ gate         │
         └──────┬───────┘
                │
                ▼
         status:review
```

### Mode A vs Mode B — Implementation Detail

| | Mode A (Isolated) | Mode B (Sequential) |
|---|---|---|
| **Context** | Fresh agent session. No conversation history. No codebase knowledge. | Full parent context. All prior conversation, codebase familiarity. |
| **What it receives** | Only what the orchestrator explicitly injects: issue body, design spec, git diff, prompt file. | Everything the parent agent saw plus the orchestrator's stage instructions. |
| **Implementation** | `pi --print "<assembled prompt>"` — a brand-new invocation with no prior session. | `pi --continue` or sub-agent API that passes parent context. For pi: extension `@mjakl/pi-subagent` with context=inherit. |
| **Use for** | TEST, VERIFY — independence is the point | IMPLEMENT — needs to see spec + codebase |
| **Anti-pattern** | Using Mode A for IMPLEMENT (agent codes blind, can't reference conventions or existing code) | Using Mode B for TEST (agent sees implementation details, writes biased tests) |

### State Machine

```
[status:ready]
     │ gh issue edit → status:design
     ▼
┌─────────┐
│ DESIGN  │── crash → on restart, find status:design, resume DESIGN
└────┬────┘
     │ git commit + gh issue edit → status:build
     ▼
┌─────────┐
│ BUILD   │── crash → on restart, find status:build, resume BUILD
└────┬────┘
     │ git commit + gh issue edit → status:verify
     ▼
┌─────────┐
│ VERIFY  │── crash → on restart, find status:verify, resume VERIFY
└────┬────┘
     │
  ┌──┴──┐
  ▼     ▼
PASS   FAIL
  │     │
  │     ▼
  │  status:blocked
  │  + blocking note
  │
  ▼
status:review
(human inspects, closes)
```

### Build Order Within BUILD Stage

Two options for TEST + IMPLEMENT under BUILD:

| Approach | How | Pros | Cons |
|----------|-----|------|------|
| **Sequential** | TEST runs first (writes test files). Then IMPLEMENT runs (writes source files). | No git conflicts. Simple. | Slower — IMPLEMENT waits for TEST. |
| **Parallel** | Both run simultaneously. TEST in git worktree A, IMPLEMENT in git worktree B. Merge after both finish. | Faster wall-clock time. | Complex merge logic. Conflict resolution needed. |

**Decision:** Phase 2 implements **sequential** (safe default). Phase 3 adds **parallel** as an optimization when git worktree isolation is implemented.

---

## 12. Implementation Sequence

### Phase 1: Core Pipeline Engine (no sub-agents yet)

**Goal:** A working `ralph daemon` that picks up a `status:ready` issue, invokes the agent with an all-in-one prompt, runs validation, and marks it `status:review`. Single Python file for the engine.

**Files to create:**

| File | Purpose |
|------|---------|
| `bin/ralph` | CLI entry point (bash). Minimal dispatcher: init, setup, daemon, status, validate, report, version, help. |
| `core/engine.py` | Pipeline engine (Python). The core loop: fetch ticket, claim, invoke agent, validate, handoff. |
| `core/init.py` | Project scaffold wizard. Generates the project tree from Section 8. No beads. |
| `core/setup.py` | `ralph setup` implementation. Checks prerequisites, creates local dirs. |
| `core/status.py` | `ralph status` dashboard. Shows daemon PID, active issue, recent metrics. |
| `core/report.py` | `ralph report` generator. Daily/weekly summary from metrics.jsonl + gh issue history. |
| `templates/PROMPT.md` | Base agent prompt (hardcoded string in init.py, or static file). All-in-one for Phase 1. |
| `templates/AGENTS.md` | Quick reference for agents (in-repo). |
| `templates/PROGRESS.md` | Agent progress log template (in-repo). |
| `templates/config.toml` | Project config for the scaffold (in-repo). |
| `scripts/install.sh` | Symlink `bin/ralph` into PATH. |

**Phase 1 checkpoint schema (`.ralph/checkpoint.json`):**

```json
{
  "issue": "31",
  "pre_commit_sha": "abc1234",
  "started_at": "2026-06-14T10:30:00Z"
}
```

In Phase 1 there is only one stage, so no `stage` field. The checkpoint exists only to know which issue was in-flight and what commit to roll back to. If the daemon starts and finds a checkpoint, it rolls back to `pre_commit_sha`, marks the issue `status:blocked` with note "interrupted", and continues.

**Phase 1 agent prompt assembly:**

Phase 1 has ONE agent invocation per issue (no stages). The prompt is:

```
PROMPT.md (base rules + conventions)
  +
Issue body (from gh issue view --json body)
  +
"Run ralph validate --tier=targeted when done."
```

The agent is instructed to: understand the issue, implement code, write tests, run validation, commit, and close the issue (mark `status:review`). The orchestrator handles label changes — the agent does NOT call `gh issue edit`.

**Build steps:**

1. **Clean scaffold** — New `ralph init` without beads references
2. **Ticket fetcher** — `gh issue list` wrapper with label filtering + ordering
3. **Single-stage loop** — One agent invocation per issue (all-in-one, like v1)
4. **Label management** — Issue status transitions via `gh issue edit`
5. **Validation gate** — Port `ralph_validate.sh` (cleanly)
6. **Daemon wrapper** — PID-file singleton, signal handling
7. **Crash recovery** — Checkpoint file tracking issue + pre-commit SHA

**Acceptance criteria:** `ralph daemon` picks up a `status:ready` issue, invokes the agent, runs validation, marks it `status:review`. The agent does not touch GitHub labels — the orchestrator does.

### Phase 2: 3-Stage Pipeline

**Goal:** Split the single invocation into DESIGN → BUILD → VERIFY with distinct persona prompts.

**Phase 2 checkpoint schema (`.ralph/checkpoint.json`):**

```json
{
  "issue": "31",
  "stage": "design|build|verify",
  "pre_stage_sha": "abc1234",
  "started_at": "2026-06-14T10:30:00Z"
}
```

**Files to modify:**

| File | Change |
|------|--------|
| `core/engine.py` | Split `run_pipeline()` into `run_design()`, `run_build()`, `run_verify()` |
| `templates/prompts/design.md` | New — Architect persona prompt |
| `templates/prompts/build.md` | New — Developer persona prompt (Phase 2 has no sub-agents yet, so BUILD is one agent) |
| `templates/prompts/verify.md` | New — Independent reviewer persona prompt |
| `core/init.py` | Generate the 3 prompt files during scaffold |

**Build steps:**

1. Split the single invocation into DESIGN → BUILD → VERIFY
2. Each stage gets a distinct persona prompt
3. Stage state tracked in checkpoint file
4. Resume from any incomplete stage after crash

**Acceptance criteria:** An issue progresses through all 3 stages sequentially. Interrupting during DESIGN resumes at DESIGN on restart. Labels transition: `status:ready` → `status:design` → `status:build` → `status:verify` → `status:review`.

### Phase 3: Sub-Agents

**Goal:** Replace single-agent BUILD/VERIFY stages with sub-agents in Mode A (isolated) and Mode B (sequential).

**Files to modify:**

| File | Change |
|------|--------|
| `core/engine.py` | `run_build()` spawns two sub-agents. `run_verify()` spawns one sub-agent in Mode A. |
| `templates/prompts/test.md` | New — QA Engineer persona prompt (Mode A sub-agent for BUILD) |
| `templates/prompts/implement.md` | New — Developer persona prompt (Mode B sub-agent for BUILD) |
| `templates/prompts/verify.md` | Update — Independent reviewer (now Mode A sub-agent instead of inline) |
| `templates/prompts/design.md` | Unchanged — DESIGN is still parent agent |

**Build steps:**

1. TEST sub-agent (Mode A — isolated, pi-subagent extension)
2. IMPLEMENT sub-agent (Mode B — sequential context)
3. VERIFY sub-agent (Mode A — isolated)
4. Parallel TEST + IMPLEMENT within BUILD stage (if git worktree isolation is ready)

**Acceptance criteria:** TEST writes tests from spec without seeing implementation. VERIFY does independent review. Both use Mode A (fresh context).

---

## 13. Acceptance Criteria (Full System)

1. `ralph init` scaffolds a project with zero beads references.
2. `ralph daemon` starts a background loop that:
   - Fetches the lowest-numbered `status:ready` issue via `gh`
   - Runs the 3-stage pipeline (DESIGN → BUILD → VERIFY)
   - Updates issue labels at each stage transition
   - On success: marks issue `status:review` for human review
   - On failure: marks issue `status:blocked` with notes
3. The GitHub Kanban board reflects issue status in real time.
4. Crash during any stage recovers cleanly on restart (resumes from incomplete stage).
5. `ralph status` shows: daemon PID, active issue, active stage, recent metrics.
6. `ralph validate --tier=targeted` runs affected tests + lint on changed files.
7. `ralph report` generates daily/weekly summary from metrics + issue history.
8. All BUILD_<feature>.md reference docs are optional and versioned in the repo.
9. Zero `bd` or `dolt` references anywhere in the system, docs, or templates.

---

*Draft — updated 2026-06-14. Continue brainstorming.*
