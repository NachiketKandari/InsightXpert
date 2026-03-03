#!/bin/sh
set -e

exec uv run uvicorn insightxpert.main:app --host 0.0.0.0 --port ${PORT:-8080}
