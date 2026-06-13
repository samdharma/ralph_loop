## VERIFY Session — Validate, Review, Close

**You are in the VERIFY phase. Run the full validation gate, perform a final quality review, and close the ticket only if everything passes.**

---

### Pre-Flight

1. **Read the ticket** — review the original acceptance criteria.
2. **Read the design and implementation notes** from `docs/agent/PROGRESS.md`.

### Workflow

1. **Run the full validation gate**:
   ```bash
   ralph validate --tier=full
   ```
2. **Check every acceptance criterion** from the ticket explicitly.
3. **Run integration tests** if applicable:
   ```bash
   ralph validate --tier=integration
   ```
4. **Perform a final review pass** (see Five-Axis Review below).
5. **Simplify** if the code is harder to read or maintain than it should be — but preserve exact behavior.
6. **If ALL checks pass**: close the ticket, commit final doc changes, update `PROGRESS.md`.
7. **If ANY check fails**: document failures in `PROGRESS.md`, update the ticket, do NOT close it.

### Five-Axis Review

Check each changed file against:

1. **Correctness** — does it do what the spec says?
2. **Simplicity** — can it be simpler without behavior change?
3. **Tests** — are there tests for new behavior and edge cases?
4. **Security** — any injection, auth, secrets, input-validation issues?
5. **Maintainability** — naming, comments, structure, no duplication.

### Security Red Flags

- User input used without validation
- Secrets or credentials in code
- Weak auth checks or missing authorization
- New dependencies without review
- Unsafe deserialization or dynamic execution

### Simplification Rules

- Don't remove code you don't fully understand (Chesterton's Fence).
- Prefer deleting code to adding it.
- A function over 500 lines is a warning sign.
- Cleverness is expensive — prefer the obvious solution.

### Performance Rule

**Measure first.** Do not optimize without data. If performance is a concern, profile before changing code.

### Acceptance Criteria Checklist

For each criterion in the ticket description, report:
```
  [PASS] criterion description
  [FAIL] criterion description — reason
```

### Anti-Rationalization

| Excuse | Reality |
|--------|---------|
| "It's too late to change this." | Better to fix before merge than after production. |
| "The tests pass, so it's fine." | Tests prove behavior, not that the code is simple or secure. |
| "This refactor is small enough to include." | Verify is for validation, not new features. |

### What You MUST NOT Do

- ❌ Do NOT close the ticket if any check fails.
- ❌ Do NOT add new features during verify.
- ❌ Do NOT skip the review pass.

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```
