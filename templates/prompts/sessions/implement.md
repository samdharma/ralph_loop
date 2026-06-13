## IMPLEMENT Session — Write Code To Pass Existing Tests

**You are in the IMPLEMENT phase. Functional and system tests already exist (written in the TEST phase). Your job is to write the minimal code that makes them pass, plus unit tests for internal logic.**

---

### Workflow

Build in thin vertical slices:

1. **Implement** the smallest complete piece of functionality.
2. **Test** — run the targeted tests.
3. **Verify** — confirm the slice works (tests pass, build succeeds).
4. **Commit** — save your progress with a descriptive message.
5. **Move to the next slice.** Repeat until the feature is complete.

Each slice should:
- Change one logical thing at a time.
- Leave the project in a buildable, testable state.
- Be independently revertable.

### Pre-Flight

1. **Read the DESIGN plan** from `docs/agent/PROGRESS.md` — look for the latest DESIGN iteration.
2. **Read the TEST plan** from `docs/agent/PROGRESS.md` — look for the latest TEST iteration.
3. **Confirm understanding** — you know what to build AND what tests must pass.

### Implementation Rules

- **Run the existing functional tests FIRST** — confirm they FAIL. If any pass, flag it.
- **Write the minimal code** to make tests pass. Don't over-engineer.
- **Write unit tests** for internal logic, edge cases, and error handling. Place them in `tests/unit/`.
- **Keep it compilable** — existing tests must pass after each slice.
- **Feature flags for incomplete features** — if the feature isn't ready for users, hide it behind a flag so increments can merge safely.

### Simplicity Check

Before finishing each slice, ask:
- Can this be done in fewer lines?
- Are these abstractions earning their complexity?
- Would a staff engineer look at this and say "why didn't you just..."?
- Am I building for hypothetical future requirements?

### Scope Discipline — Do NOT

- Remove comments you don't understand.
- "Clean up" code orthogonal to the task.
- Refactor adjacent systems as a side effect.
- Add features not in the spec because they "seem useful".

### Anti-Rationalization

| Excuse | Reality |
|--------|---------|
| "I'll test it all at the end." | Bugs compound. Test each slice. |
| "It's faster to do it all at once." | It feels faster until something breaks in 500 changed lines. |
| "These changes are too small to commit separately." | Small commits are free. Large commits hide bugs. |

### What You MUST NOT Do

- ❌ Do NOT modify functional/system tests written in the TEST phase (except for compilation fixes).
- ❌ Do NOT close the ticket (verification is a separate session).
- ❌ Do NOT run the full test suite or e2e/performance tests.
- ❌ Do NOT refactor beyond what the design plan specifies.
- ❌ Do NOT commit broken code.

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```
