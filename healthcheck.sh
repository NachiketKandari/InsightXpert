#!/bin/bash
PORT=8000

response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:${PORT}/" 2>/dev/null)
# 404 means server is up and responding (FastAPI has no root route)
# 000 means connection refused — server is dead
if [ "$response" = "000" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') | FAIL: connection refused, restarting..."
    /home/nachiket/projects/insightxpert/start.sh
    exit 1
fi
echo "$(date '+%Y-%m-%d %H:%M:%S') | OK: server up (HTTP $response)"
exit 0
