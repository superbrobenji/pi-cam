# Venv Setup and Boot Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `install.sh` and a systemd service so the Pi people detector installs with a virtualenv and auto-starts at boot with a one-retry crash policy.

**Architecture:** `install.sh` creates a virtualenv, installs deps, writes a systemd unit file with the resolved user and working directory, then enables and starts the service. All paths are resolved at install time — no template substitution files needed. README is updated to replace the broken `pip install` instruction.

**Tech Stack:** bash, Python venv, systemd

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `install.sh` | Create | Create venv, install deps, write + enable systemd service |
| `README.md` | Modify | Replace setup section, add service management section |

---

### Task 1: Create `install.sh`

**Files:**
- Create: `install.sh`

- [ ] **Step 1: Write `install.sh`**

```bash
#!/usr/bin/env bash
set -e

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

[Install]
WantedBy=multi-user.target
EOF

echo "[4/4] Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo ""
echo "Done. Service status:"
systemctl status "$SERVICE_NAME" --no-pager
```

- [ ] **Step 2: Make executable**

```bash
chmod +x install.sh
```

- [ ] **Step 3: Verify shell syntax**

```bash
bash -n install.sh
```

Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add install.sh
git commit -m "feat: add install.sh for venv setup and systemd service"
```

---

### Task 2: Update `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace Setup section and add Service Management section**

Replace the entire `## Setup` section:

```markdown
## Setup

Run once on the Pi:

```bash
chmod +x install.sh
./install.sh
```

This creates a `venv/`, installs dependencies, and registers the app as a systemd service that starts at boot.

### Development (no Pi)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
```

Add after the `## Running` section:

```markdown
## Service Management

```bash
# View live logs
journalctl -u pi-people-detector -f

# Stop the service
sudo systemctl stop pi-people-detector

# Start the service
sudo systemctl start pi-people-detector

# Disable autostart
sudo systemctl disable pi-people-detector
```

The service restarts once automatically on crash. If it crashes again within 60 seconds, it stays stopped. Run `sudo systemctl reset-failed pi-people-detector` to clear the failure state and allow restarts again.
```

- [ ] **Step 2: Verify README renders correctly**

```bash
cat README.md
```

Check: no raw placeholder text, setup section points to `install.sh`, service management section present.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update setup instructions to use install.sh and venv"
```

---

## On-Pi Verification

Run these on the Pi after cloning the repo:

```bash
# Install
chmod +x install.sh
./install.sh

# Confirm service running
systemctl is-active pi-people-detector
# Expected: active

# Confirm venv exists and has packages
./venv/bin/pip list | grep uvicorn
# Expected: uvicorn  <version>

# Confirm service restarts on crash
sudo kill -9 $(systemctl show -p MainPID pi-people-detector | cut -d= -f2)
sleep 3
systemctl is-active pi-people-detector
# Expected: active  (restarted once)

# Confirm UI accessible from another machine
# Open http://<pi-ip>:8000 in browser
```
