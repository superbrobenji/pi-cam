# Venv Setup and Boot Service Design

**Date:** 2026-06-02

## Problem

Current `README.md` instructs `pip install -r requirements.txt` system-wide, which fails on modern Debian-based systems (Raspberry Pi OS Bookworm) with "externally managed environment" error. No boot service exists, so the app must be started manually after each reboot.

## Goals

- Correct dependency installation using a virtualenv
- App starts automatically at boot
- App restarts once on crash; stays dead after a second consecutive crash
- Single script to run on a fresh Pi

## New Files

### `install.sh`

Shell script run once on the Pi to set up the environment and install the systemd service.

Steps:
1. Create `venv/` in repo root via `python3 -m venv venv`
2. Install deps: `venv/bin/pip install -r requirements.txt`
3. Copy `pi-people-detector.service` to `/etc/systemd/system/`
4. Run `systemctl daemon-reload && systemctl enable --now pi-people-detector`

Script uses `set -e` to abort on any failure. Prints status at each step.

### `pi-people-detector.service`

systemd unit file with the following config:

```ini
[Unit]
Description=Pi People Detector
After=network.target

[Service]
Type=simple
User=<current user>
WorkingDirectory=<repo root>
ExecStart=<repo root>/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
StartLimitBurst=2
StartLimitIntervalSec=60

[Install]
WantedBy=multi-user.target
```

`StartLimitBurst=2` + `StartLimitIntervalSec=60`: allows 1 restart within 60s window; killed permanently on 2nd failure. Counter resets if service stays up for 60s.

Runs as the installing user, not root.

## README Changes

Replace setup section:

```bash
pip install -r requirements.txt
```

With:

```bash
chmod +x install.sh
./install.sh
```

Add section for managing the service (start/stop/logs).

## Out of Scope

- Multiple user support
- Environment variable configuration (MOCK_CAMERA etc.) — can be added later via systemd `Environment=` directive
- Port configuration
