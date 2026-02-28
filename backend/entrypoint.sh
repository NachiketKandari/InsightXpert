#!/bin/sh
set -e

DB_PATH="/app/insightxpert.db"

if [ -n "$LITESTREAM_REPLICA_URL" ]; then
    litestream restore -if-replica-exists -config /app/litestream.yml "$DB_PATH"
    exec litestream replicate -exec "uv run uvicorn insightxpert.main:app --host 0.0.0.0 --port ${PORT:-8080}" -config /app/litestream.yml
else
    exec uv run uvicorn insightxpert.main:app --host 0.0.0.0 --port ${PORT:-8080}
fi
