#!/bin/sh
# Restore the production SQLite DB from GCS Litestream replica.
# Usage: ./scripts/db-restore.sh [output-path]
#
# Opens the restored DB in your default SQLite GUI (DB Browser) if installed,
# otherwise prints the path so you can open it manually.

set -e

REPLICA_URL="gcs://insightxpert-bucket/litestream/insightxpert.db"
OUTPUT="${1:-/tmp/insightxpert-prod.db}"

# Find litestream
LITESTREAM="${LITESTREAM:-$(command -v litestream 2>/dev/null || echo "$HOME/bin/litestream")}"
if [ ! -x "$LITESTREAM" ]; then
    echo "Error: litestream not found. Install it:"
    echo "  curl -fsSL https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-darwin-arm64.zip -o /tmp/ls.zip"
    echo "  unzip /tmp/ls.zip -d ~/bin"
    exit 1
fi

echo "Restoring production DB from $REPLICA_URL ..."
"$LITESTREAM" restore -o "$OUTPUT" "$REPLICA_URL"
echo "Restored to: $OUTPUT"

# Try to open in DB Browser for SQLite (macOS)
if [ "$(uname)" = "Darwin" ] && [ -d "/Applications/DB Browser for SQLite.app" ]; then
    open -a "DB Browser for SQLite" "$OUTPUT"
    echo "Opened in DB Browser for SQLite"
elif command -v sqlite3 >/dev/null 2>&1; then
    echo "Run:  sqlite3 $OUTPUT"
fi
