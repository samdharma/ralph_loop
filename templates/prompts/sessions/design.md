## DESIGN Session — Analyze, Plan, Document

**You are in the DESIGN phase. Do NOT write implementation code.**

### Your Job

1. **Read & understand** the ticket description, acceptance criteria, and any referenced specs.
2. **Research** the codebase — identify affected modules, files, and dependencies.
3. **Plan** the implementation:
   - What files need to change?
   - What new files are needed?
   - What tests need to be written?
   - What are the edge cases and risks?
4. **Document your design** in `docs/agent/PROGRESS.md` under a new iteration entry.
5. **Update the ticket** with design notes:
   ```bash
   bd update <TASK_ID> --notes="Design complete. See PROGRESS.md for plan."
   ```

### What You MUST NOT Do

- ❌ Do NOT write implementation code.
- ❌ Do NOT modify source files (except PROGRESS.md and ticket notes).
- ❌ Do NOT run the validation gate.
- ❌ Do NOT close the ticket.

### Deliverables

- `docs/agent/PROGRESS.md` updated with a design plan including:
  - **Files to modify** (with paths)
  - **New files to create** (with paths)
  - **Test plan** (what tests need to exist)
  - **Risks & edge cases**
  - **Estimated complexity** (trivial / small / medium / large)

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```
