# CLAUDE.md

Behavioral guidelines for working in this repository. Keep them strict, practical, and minimal.

## 1. Before Coding

- Do not assume unclear requirements.
- State assumptions when they matter.
- If multiple interpretations are plausible, surface them instead of picking silently.
- If the simpler solution is sufficient, use it.
- If something important is unclear or risky, stop and ask.

For multi-step work, define a short verification-driven plan:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

## 2. During Changes

- Make the smallest change that fully solves the task.
- Do not add features, abstractions, or configurability that were not requested.
- Match the local style of the file you are editing.
- Do not refactor adjacent code unless the task requires it.
- Remove only the unused code created by your own change.
- If you notice unrelated problems, mention them instead of fixing them opportunistically.

Every changed line should trace directly to the request.

## 3. Documentation Workflow

Before any non-trivial task:

1. Read [`README.md`](README.md).
2. Read the relevant local documentation for the area you are changing, if it exists.

### Update docs when behavior or structure changes

Update the relevant doc whenever you change documented architecture or behavior, including:

- public APIs
- data formats or schemas
- configuration
- major user or developer workflows

If docs and code disagree:

- trust code for current behavior
- update docs in the same change
- mention the mismatch in the final note

### Doc format

- Start with a one-paragraph overview.
- Link to concrete files with relative paths.
- Use tables for schema, config, or file maps when helpful.
- Use short ASCII flow diagrams when helpful.
- Document what exists now, not what was once planned.

## 4. Testing

After every code change, run tests or the most relevant validation available.

Rules:

- Run the smallest relevant test or validation that gives confidence in the change.
- If the repository defines multiple test suites, run the ones affected by the change.
- When in doubt, run everything.
- If you intentionally change documented behavior, update the code, the docs, and the tests together when applicable.
- Add tests for non-trivial logic that is easy to regress.
- Do not add tests for trivial code.
- A task is not complete while required tests are failing.

## 5. Project-Specific Guidance

Prefer generic, reusable project structure and documentation unless the user asks for repository-specific conventions.

## 6. Language

- Default to Russian in chat replies, progress updates, and final summaries unless the user asks for another language.
- When changing UI copy or settings, keep Russian and English support in mind and preserve parity between both languages.
