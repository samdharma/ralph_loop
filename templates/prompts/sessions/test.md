## TEST Session — Write Functional & System Tests From Design

**You are in the TEST phase. Write tests from the design specification — NOT from implementation code (there is none).**

### Your Job

1. **Read the DESIGN plan** from `docs/agent/PROGRESS.md` — find the latest DESIGN iteration.
2. **Read the ticket** — understand the acceptance criteria.
3. **Write functional, system, and integration tests** based on the design spec and acceptance criteria:
   - **Functional tests**: Test the feature's behavior from the user's perspective. What inputs? What outputs? What side effects?
   - **System / Integration tests**: Test how this feature interacts with other modules, APIs, or databases.
   - **Edge case tests**: Boundary conditions, error handling, null/empty inputs, concurrency issues.
4. **Write tests that SHOULD FAIL** — there is no implementation yet. These tests prove the feature is needed.
5. **Document the test plan** in `docs/agent/PROGRESS.md`:
   - Test file locations
   - What each test verifies
   - Which acceptance criteria each test covers
   - Expected failure modes (since implementation doesn't exist yet)
6. **Do NOT write implementation code, mocks, or stubs** beyond what tests need to compile.

### Test Writing Guidelines

- **Test the spec, not the code.** Derive tests from the acceptance criteria and design plan.
- **Be explicit about expected behavior.** What exact output for what exact input?
- **Cover all acceptance criteria.** Every criterion in the ticket must have at least one test.
- **Write integration tests** that test the feature's contract with other modules.
- **Use descriptive test names** that document the expected behavior.
- **Place tests in the correct directories** (unit/, integration/, e2e/ as appropriate).

### Test Coverage Map

For each acceptance criterion in the ticket, map it to at least one test:
```
  Criterion: "User can reset password via email"
  → tests/integration/test_password_reset.py::test_reset_email_sent
  → tests/integration/test_password_reset.py::test_reset_token_valid
  → tests/unit/test_password_reset.py::test_token_expiry
```

### What You MUST NOT Do

- ❌ Do NOT write implementation code. NONE. There is no implementation yet.
- ❌ Do NOT write unit tests for internal logic (that's the IMPLEMENT session's job).
- ❌ Do NOT mock or stub the feature — test real behavior.
- ❌ Do NOT run the validation gate (tests will fail — that's expected).
- ❌ Do NOT close the ticket.

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```
