#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TMPDIR=$(mktemp -d)
cleanup() {
  rm -rf -- "$TMPDIR"
}
trap cleanup EXIT

cd -- "$ROOT"

uv sync --locked --all-extras
uv run ruff format --check .
uv run ruff check .
uv run pytest
rm -rf -- dist
uv run python -m build
uv run python -m jobloom.release_check dist public-files

python -m venv "$TMPDIR/venv"
"$TMPDIR/venv/bin/python" -m pip install "$ROOT/dist/jobloom-0.1.0-py3-none-any.whl"
"$TMPDIR/venv/bin/jobloom" --version
XDG_CONFIG_HOME="$TMPDIR/config" XDG_STATE_HOME="$TMPDIR/state" "$TMPDIR/venv/bin/jobloom" providers
