## Docs-Specific Guidance

- **No test runner needed**: If your change touches ONLY documentation/HTML/markdown, you may skip the full test suite.
- **Still run the validation gate**: `ralph validate --tier=smoke` is sufficient for doc-only changes.
- **Consistency**: Ensure terminology matches the rest of the docs.
- **Accuracy**: Verify all CLI commands, file paths, and version numbers are current.
