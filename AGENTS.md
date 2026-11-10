# AGENTS.md

- Use `uv` for dependency management and Python commands. Commit `uv.lock`.
- Keep tools read-only and document upstream API behavior, data provenance, and usage terms.
- Before pushing, run `uv sync --locked`, `uv run ruff check .`, `uv run ty check`, `uv run pytest`, and `uv build`.
- Keep CI tests offline. Validate changes to the upstream contract separately with a small read-only sample.
