#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../backend"
.venv/bin/ruff check src tests migrations
.venv/bin/ruff format --check src tests migrations
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/pytest -q
