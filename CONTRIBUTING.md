# Contributing

Keep repository text, code, tests, metadata, and docs in English. Do not add live job-board calls to tests. Do not add account-mutating behavior such as applying, form submission, messaging, or profile modification.

Useful local checks:

```bash
uv sync --locked --all-extras
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python -m build
scripts/release-check.sh
```
