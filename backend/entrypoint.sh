#!/bin/sh
set -e

DB_PATH="/app/insightxpert.db"
SEED_BUCKET="insightxpert-bucket"
SEED_OBJECT="seed%2Finsightxpert.db"

if [ -n "$LITESTREAM_REPLICA_URL" ]; then
    # Try restoring from Litestream replica first
    litestream restore -if-replica-exists -config /app/litestream.yml "$DB_PATH"

    # If no replica existed yet, download the seed DB from GCS
    if [ ! -f "$DB_PATH" ]; then
        echo "No Litestream replica found. Downloading seed DB from GCS..."
        TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
            | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
        curl -sf -H "Authorization: Bearer $TOKEN" \
            "https://storage.googleapis.com/storage/v1/b/${SEED_BUCKET}/o/${SEED_OBJECT}?alt=media" \
            -o "$DB_PATH"
        echo "Seed DB downloaded successfully"
    fi

    exec litestream replicate -exec "uv run uvicorn insightxpert.main:app --host 0.0.0.0 --port ${PORT:-8080}" -config /app/litestream.yml
else
    exec uv run uvicorn insightxpert.main:app --host 0.0.0.0 --port ${PORT:-8080}
fi
