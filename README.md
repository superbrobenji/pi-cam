# Pi People Detector

Detects people in a webcam frame using YOLOv8 and broadcasts a live count over WebSocket. Includes a web UI with device health stats and optional MJPEG camera preview.

## Requirements

- Python 3.11+
- Raspberry Pi 5 (or any Linux/macOS machine for dev)
- USB webcam (for live mode)

## Setup

```bash
pip install -r requirements.txt
```

## Running

### On the Pi (live camera)

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://<pi-ip>:8000` in a browser on your local network.

### Development (no camera)

```bash
MOCK_CAMERA=1 uvicorn main:app --reload --port 8000
```

### Tests

```bash
pytest -v
```

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
