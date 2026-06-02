#!/usr/bin/env bash
set -e

[[ $EUID -ne 0 ]] || { echo "Error: do not run install.sh as root"; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="pi-people-detector"
MONITOR_NAME="pi-monitor"

echo "[1/5] Creating virtualenv..."
python3 -m venv "$REPO_DIR/venv"

echo "[2/5] Installing dependencies..."
"$REPO_DIR/venv/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"

echo "[3/5] Installing detector service..."
sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null <<EOF
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

echo "[4/5] Installing monitor service..."
sudo tee "/etc/systemd/system/${MONITOR_NAME}.service" > /dev/null <<EOF
[Unit]
Description=Pi People Detector Monitor
After=network.target
StartLimitBurst=2
StartLimitIntervalSec=60

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${REPO_DIR}
ExecStart=${REPO_DIR}/venv/bin/uvicorn monitor:app --host 0.0.0.0 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[5/5] Enabling and starting services..."
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sudo systemctl enable --now "$MONITOR_NAME"

echo ""
echo "Done."
systemctl status "$SERVICE_NAME" --no-pager || true
systemctl status "$MONITOR_NAME" --no-pager || true
