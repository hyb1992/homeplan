# Repository guidance

Keep financial inputs, exports, databases, backups and browser profiles out of Git.
Use synthetic fixtures for tests. SQLite is authoritative; Excel is import-only.
Keep core calculations free of I/O and clocks. Use integer won and Decimal.
Validate with uv run ruff check ., uv run ruff format --check ., uv run mypy src/homeplan, uv run pytest -q, and node --test tests/web/test_form_inputs.mjs.
main deploys Pages and Windows automatically after checks. Preserve data during updates.
