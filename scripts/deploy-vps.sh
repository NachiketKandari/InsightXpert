#!/bin/bash
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────
REPO_URL="https://github.com/NachiketKandari/InsightXpert.git"
APP_DIR="/opt/insightxpert/repo"
ENV_FILE="${APP_DIR}/backend/.env.local"
SERVICE_NAME="insightxpert"
DOMAIN="api.insightxpert.in"

echo "=== InsightXpert VPS Deploy ==="

# ── Clone or pull ────────────────────────────────────────────────
if [ -d "${APP_DIR}/.git" ]; then
    echo "→ Pulling latest changes..."
    cd "${APP_DIR}"
    git pull origin master
else
    echo "→ Cloning repo..."
    git clone "${REPO_URL}" "${APP_DIR}"
    cd "${APP_DIR}"
fi

# ── Backend setup ────────────────────────────────────────────────
cd "${APP_DIR}/backend"

if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: ${ENV_FILE} not found. Create it first with your secrets."
    echo "Template:"
    echo "  DEEPSEEK_API_KEY=sk-..."
    echo "  SECRET_KEY=<random-64-char-string>"
    echo "  ADMIN_SEED_EMAIL=admin@insightxpert.in"
    echo "  ADMIN_SEED_PASSWORD=<strong-password>"
    echo "  CORS_ORIGINS=https://insightxpert.in,https://www.insightxpert.in"
    exit 1
fi

# Sync dependencies
if command -v uv &>/dev/null; then
    uv sync --frozen --no-dev
else
    pip install -r requirements.txt 2>/dev/null || pip install -e .
fi

# ── Systemd service ──────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -f "${SERVICE_FILE}" ]; then
    echo "→ Installing systemd service..."
    cat > /tmp/${SERVICE_NAME}.service << SERVICEOF
[Unit]
Description=InsightXpert API Backend
After=network.target

[Service]
Type=simple
User=nachiket
WorkingDirectory=${APP_DIR}/backend
EnvironmentFile=${ENV_FILE}
ExecStart=${APP_DIR}/backend/.venv/bin/uvicorn insightxpert.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICEOF
    sudo mv /tmp/${SERVICE_NAME}.service "${SERVICE_FILE}"
    sudo systemctl daemon-reload
    sudo systemctl enable "${SERVICE_NAME}"
fi

echo "→ Restarting service..."
sudo systemctl restart "${SERVICE_NAME}"

# ── Health check ─────────────────────────────────────────────────
sleep 2
echo "→ Health check..."
curl -sf http://localhost:8000/health && echo "" && echo "✓ Backend healthy"
curl -sf https://${DOMAIN}/health && echo "" && echo "✓ Public endpoint reachable"

echo ""
echo "=== Deploy complete ==="
echo "API:    https://${DOMAIN}"
echo "Docs:   https://${DOMAIN}/docs"
echo "Status: sudo systemctl status ${SERVICE_NAME}"
echo "Logs:   sudo journalctl -u ${SERVICE_NAME} -f"
