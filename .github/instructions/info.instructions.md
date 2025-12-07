---
applyTo: '**'
---

## Project Philosophy

- **Agile:** iterate, adapt, deliver user value quickly.
- **First Principles:** question assumptions, work only with facts, prefer simple testable solutions.
- **No Assumptions:** LLM must ask for clarification; no speculation or off-rails reasoning allowed.

## Implementation Guidelines

- Ask clarifying questions for any ambiguity.
- Work only with facts; no assumptions.
- Deliver small, testable increments; keep code simple and readable.
- Explain design rationale; validate with tests.

## Environment & Dependencies (uv by Astral)

- Manage all deps via `pyproject.toml`; commit `uv.lock`.
- Use `uv run` and `uv sync` for environment setup and execution.
- No manual venv or pip; uv is source of truth.

---