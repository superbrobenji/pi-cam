# Pi People Detector

Detects people in a webcam frame using YOLOv8 and broadcasts a live count over WebSocket. A separate management dashboard at port 8001 provides component health, error logs, and restart controls.

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

After `install.sh`, both services start automatically:

| Service | URL | Description |
|---|---|---|
| `pi-people-detector` | `http://<pi-ip>:8000` | Detector API (WebSocket, health, stream) |
| `pi-monitor` | `http://<pi-ip>:8001` | Management dashboard |

Open `http://<pi-ip>:8001` in a browser to access the dashboard.

### Manual run (debugging only — stop services first)

```bash
sudo systemctl stop pi-people-detector pi-monitor
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
./venv/bin/uvicorn monitor:app --host 0.0.0.0 --port 8001
```

### Development (no camera)

With the venv active (`source venv/bin/activate`):

```bash
MOCK_CAMERA=1 uvicorn main:app --reload --port 8000
uvicorn monitor:app --reload --port 8001
```

### Tests

```bash
pytest -v
```

## Service Management

Use the dashboard at `http://<pi-ip>:8001` to restart components or view logs. For shell access:

```bash
# View live logs
journalctl -u pi-people-detector -f
journalctl -u pi-monitor -f

# Restart services
sudo systemctl restart pi-people-detector
sudo systemctl restart pi-monitor

# Check status
systemctl status pi-people-detector pi-monitor
```

Both services restart once automatically on crash. If a service crashes again within 60 seconds, it stays stopped. Run `sudo systemctl reset-failed <service-name>` to clear the failure state.

## WebSocket API

Connect to `ws://<host>:8000/ws`. Receives JSON every ~1 second:

```json
{
  "rawCount": 5,
  "enteredFrame": 2,
  "firstSeen": 1,
  "uniqueTotal": 14
}
```

| Field | Description |
|---|---|
| `rawCount` | Total people currently in frame |
| `enteredFrame` | People not present in previous tick |
| `firstSeen` | People seen for the first time this session |
| `uniqueTotal` | Cumulative unique people since app start |

See `docs/websocket-integration.md` for full integration examples.

## API Endpoints (port 8000)

| Path | Description |
|---|---|
| `WS /ws` | Live tracking data (rawCount, enteredFrame, firstSeen, uniqueTotal) every ~1s |
| `GET /stream` | MJPEG camera preview |
| `GET /health` | JSON device health snapshot |
| `GET /logs/{component}` | Last 100 log entries for `detector`, `health`, or `stream` |
| `POST /control/restart/detector` | Restart detector thread |
| `POST /control/restart/health` | Restart health poller thread |

## Monitor Endpoints (port 8001)

| Path | Description |
|---|---|
| `GET /` | Management dashboard |
| `GET /api/status` | Aggregated health + online status |
| `GET /api/logs/{component}` | Proxied log entries |
| `POST /api/restart/detector` | Restart detector via main app |
| `POST /api/restart/health` | Restart health poller via main app |
| `POST /api/restart/service` | Restart entire `pi-people-detector` service |
