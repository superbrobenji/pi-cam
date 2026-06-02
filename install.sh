#!/usr/bin/env bash
set -e

[[ $EUID -ne 0 ]] || { echo "Error: do not run install.sh as root"; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="pi-people-detector"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "[1/4] Creating virtualenv..."
python3 -m venv "$REPO_DIR/venv"

echo "[2/4] Installing dependencies..."
"$REPO_DIR/venv/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"

echo "[3/4] Installing systemd service..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Pi People Detector
After=network.target
StartLimitBurst=2
StartLimitIntervalSec=60

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${REPO_DIR}
ExecStart=${REPO_DIR}/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[4/4] Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo ""
echo "Done. Service status:"
systemctl status "$SERVICE_NAME" --no-pager || true
