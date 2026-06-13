## DESIGN Session — Analyze, Plan, Document

**You are in the DESIGN phase — the first of four stages (design → test → implement → verify). Do NOT write implementation code and do NOT write tests.**

Your job is to produce a human-reviewable plan before any code is written.

---

### Workflow

1. **Read the ticket** and any existing specs or reference docs.
2. **Surface assumptions** — list what you're assuming about requirements, architecture, or scope. Stop if you're guessing.
3. **Research the codebase** — identify affected modules, files, and dependencies.
4. **Define success criteria** — reframe vague requirements into concrete, testable conditions.
   - Bad: "Make it faster."
   - Good: "Endpoint p95 < 200ms; LCP < 2.5s."
5. **Write a design spec** covering:
   - **Objective**: what we're building and why
   - **Commands**: build, test, lint, dev commands that will be used
   - **Project structure**: files and directories that will change or be created
   - **Code style**: naming, patterns, one representative snippet
   - **Testing strategy**: what kinds of tests, where they live
   - **Boundaries**: Always / Ask first / Never rules
   - **Success criteria**: how we know it's done
   - **Open questions**: anything unresolved
6. **Document the plan** in `docs/agent/PROGRESS.md`.
7. **Update the ticket** with design notes.

### Anti-Rationalization

| Excuse | Reality |
|--------|---------|
| "This is simple, I don't need a spec." | Simple tasks still need acceptance criteria. A two-line spec is fine. |
| "I'll write the spec after I code it." | That's documentation, not specification. Specs prevent rework. |
| "The user knows what they want." | Even clear requests hide implicit assumptions. Surface them now. |

### What You MUST NOT Do

- ❌ Do NOT write implementation code.
- ❌ Do NOT write tests (functional tests are written in the TEST stage).
- ❌ Do NOT modify source files (except `PROGRESS.md` and ticket notes).
- ❌ Do NOT run the validation gate.
- ❌ Do NOT close the ticket.

### Deliverables

`docs/agent/PROGRESS.md` updated with a design plan including:
- **Files to modify** (with paths)
- **New files to create** (with paths)
- **Test plan** (what tests need to exist)
- **Boundaries** (Always / Ask first / Never)
- **Success criteria** (specific and testable)
- **Risks & edge cases**
- **Estimated complexity** (trivial / small / medium / large)

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```
