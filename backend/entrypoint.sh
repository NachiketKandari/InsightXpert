#!/bin/sh
set -e

# Database is Turso (libSQL) accessed via embedded replica. The replica file is
# materialized at TURSO_LOCAL_REPLICA_PATH on cold start and synced from the
# remote primary. No Litestream / GCS seed restore needed.
exec uv run uvicorn insightxpert.main:app --host 0.0.0.0 --port "${PORT:-8080}"
