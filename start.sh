#!/bin/bash
set -e

PROJECT_DIR="/home/nachiket/projects/insightxpert/backend"
cd "$PROJECT_DIR"

# Kill any existing processes on port 8000 (uv run wrapper + child = multiple PIDs)
existing_pids=$(pgrep -f "uvicorn insightxpert.main:app.*8000" 2>/dev/null || true)
if [ -n "$existing_pids" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') | Killing existing insightxpert-old PIDs: $(echo $existing_pids | tr '\n' ' ')"
    kill $existing_pids 2>/dev/null || true
    sleep 2
    kill -9 $existing_pids 2>/dev/null || true
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') | Starting insightxpert-old..."
nohup /home/nachiket/.local/bin/uv run uvicorn insightxpert.main:app \
    --host 127.0.0.1 --port 8000 \
    --proxy-headers --forwarded-allow-ips='*' \
    >> uvicorn.log 2>&1 &

echo "$(date '+%Y-%m-%d %H:%M:%S') | Started insightxpert-old PID $!"
