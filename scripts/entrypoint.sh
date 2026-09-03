#!/bin/bash
set -e

# The DB URL is expected to be provided via environment variable DATABASE__URL
echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting application..."
exec uv run "$@"
