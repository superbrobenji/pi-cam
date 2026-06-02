# Pi People Detector

Detects people in a webcam frame using YOLOv8 and broadcasts a live count over WebSocket. Includes a web UI with device health stats and optional MJPEG camera preview.

## Requirements

- Python 3.11+
- Raspberry Pi 5 (or any Linux/macOS machine for dev)
- USB webcam (for live mode)

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

## Running

### On the Pi (live camera)

After running `install.sh`, the app starts automatically as a service. See [Service Management](#service-management) to control it.

For manual runs (debugging only — stop the service first to avoid port conflicts):

```bash
sudo systemctl stop pi-people-detector
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

### Development (no camera)

With the venv active (`source venv/bin/activate`):

```bash
MOCK_CAMERA=1 uvicorn main:app --reload --port 8000
```

### Tests

```bash
pytest -v
```

## Service Management

```bash
# View live logs
journalctl -u pi-people-detector -f

# Stop the service
sudo systemctl stop pi-people-detector

# Start the service
sudo systemctl start pi-people-detector

# Restart the service (e.g. after a code update)
sudo systemctl restart pi-people-detector

# Check service status
systemctl status pi-people-detector

# Disable autostart
sudo systemctl disable pi-people-detector
```

The service restarts once automatically on crash. If it crashes again within 60 seconds, it stays stopped. Run `sudo systemctl reset-failed pi-people-detector` to clear the failure state and allow restarts again.

## WebSocket API

Connect to `ws://<host>:8000/ws`. Receives JSON every ~1 second:

```json
{"count": 3}
```

## Endpoints

| Path | Description |
|---|---|
| `GET /` | Web UI |
| `WS /ws` | Live people count |
| `GET /stream` | MJPEG camera preview |
| `GET /health` | JSON device health snapshot |
