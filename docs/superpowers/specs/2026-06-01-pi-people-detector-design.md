# Pi People Detector — Design Spec
_2026-06-01_

## Overview

A Python service for Raspberry Pi 5 + USB webcam. Detects people in frame using YOLOv8, broadcasts a live count over WebSocket, and serves a web UI with device health stats and an optional MJPEG camera preview.

---

## Architecture

Single FastAPI process. Two daemon threads (detector, health poller) write into a shared state object. FastAPI endpoints read from it.

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI App                       │
│                                                      │
│  ┌─────────────┐    ┌──────────────────────────┐    │
│  │ Detection   │    │       SharedState        │    │
│  │ Thread      │───▶│  count: int              │    │
│  │ (YOLO loop) │    │  frame: bytes (JPEG)     │    │
│  └─────────────┘    │  health: dict            │    │
│                     │  camera_ok: bool         │    │
│  ┌─────────────┐    │  model_ok: bool          │    │
│  │ Health      │───▶│  ws_clients: int         │    │
│  │ Thread      │    └──────────┬───────────────┘    │
│  │ (psutil)    │               │                    │
│  └─────────────┘               ▼                    │
│  ┌──────────────────────────────────────────────┐   │
│  │              HTTP Endpoints                  │   │
│  │  GET  /          → serve index.html          │   │
│  │  GET  /stream    → MJPEG camera feed         │   │
│  │  GET  /health    → JSON health snapshot      │   │
│  │  WS   /ws        → push count every 1s      │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## File Structure

```
pi-module/
├── main.py              # FastAPI app + startup
├── detector.py          # YOLO detection loop thread
├── shared_state.py      # Thread-safe state container
├── health.py            # psutil health polling thread
├── static/
│   └── index.html       # Web UI (vanilla JS, no build step)
├── requirements.txt
└── README.md
```

---

## Components

### shared_state.py
Thread-safe container using `threading.Lock`. Holds:
- `count: int` — current people in frame
- `frame: bytes` — latest JPEG-encoded frame
- `camera_ok: bool` — camera connected and reading
- `model_ok: bool` — YOLOv8 loaded successfully
- `ws_clients: int` — number of active WebSocket connections
- `cpu_percent: float` — latest CPU usage
- `ram_used: int`, `ram_total: int` — bytes

### detector.py
Daemon thread. Loop:
1. Capture frame via OpenCV (`cv2.VideoCapture`)
2. Encode frame as JPEG, write to SharedState
3. Run YOLOv8 inference (`ultralytics.YOLO`)
4. Filter results to class `"person"`, confidence ≥ 0.5
5. Write `count` to SharedState
6. Sleep to target ~1s cycle time

On any exception: set `camera_ok=False`, backoff 2s, retry.  
After successful model load: set `model_ok=True`.

`MOCK_CAMERA=1` env var skips OpenCV and feeds a static test JPEG — enables CI testing without hardware.

### health.py
Daemon thread. Every 2s: sample `psutil.cpu_percent()`, `psutil.virtual_memory()`, write to SharedState.

### main.py
FastAPI app:
- Starts detector and health threads on `startup` event
- `GET /` — serves `static/index.html`
- `GET /stream` — async generator, reads latest frame from SharedState every 100ms, streams as `multipart/x-mixed-replace`
- `GET /health` — returns JSON snapshot of all SharedState health fields
- `WS /ws` — adds client to set, background task broadcasts `{"count": N}` every 1s, removes client on disconnect

---

## Data Flow

**Detection cycle (~1s):**
```
OpenCV capture → JPEG encode → SharedState.frame
                             → YOLOv8 inference → filter persons → SharedState.count
```

**WebSocket push (every 1s):**
```
SharedState.count → {"count": N} → all connected WS clients
```

**MJPEG stream (while client connected):**
```
SharedState.frame (latest) → multipart chunk → browser <img>
```

**Health cycle (every 2s):**
```
psutil → SharedState.{cpu, ram, camera_ok, model_ok, ws_clients}
```

---

## Web UI

Single `index.html`, vanilla JS, no build step.

Layout:
```
┌─────────────────────────────────────────┐
│           Pi People Counter             │
├─────────────────────────────────────────┤
│         PEOPLE IN FRAME                 │
│              [ 3 ]                      │
├──────────────┬──────────────────────────┤
│ Health       │                          │
│ CPU:  45%    │   [ Camera Preview ]     │
│ RAM:  62%    │   (click to open/close)  │
│ Camera:  ✓   │                          │
│ YOLOv8:  ✓   │                          │
│ WebSocket: ✓ │                          │
└──────────────┴──────────────────────────┘
```

Behaviour:
- Count updates live via WebSocket — no polling
- Health panel polls `GET /health` every 3s, red/green indicators
- Camera preview off by default — toggle button sets `<img src="/stream">` to open, clears `src` to close (stops bandwidth)
- WebSocket auto-reconnects on drop with exponential backoff: 1s → 2s → 4s → max 30s

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Camera disconnects | `camera_ok=False`, thread retries every 2s, UI shows red |
| YOLO inference error | Log, skip frame, continue — count unchanged |
| YOLO fails to load | `model_ok=False`, app still starts, UI shows red |
| WebSocket client drops | Silently removed from client set |
| `/stream` client disconnects | Async generator exits cleanly |

---

## Testing

**Unit:**
- `shared_state.py` — concurrent read/write thread-safety
- `health.py` — output shape and types

**Integration (no hardware required):**
- Start app with `MOCK_CAMERA=1`
- Assert WebSocket emits `{"count": N}`
- Assert `GET /health` returns all expected keys with correct types
- Assert `GET /stream` returns `multipart/x-mixed-replace` content-type

**Manual on Pi:**
- Real webcam, verify count accuracy
- Verify MJPEG preview renders in browser
- Verify health stats reflect actual device load

---

## Future: Unique Person Re-ID

Designed for extension. When re-ID is added:
- Detector thread gains a tracker (e.g. DeepSORT or ByteTrack)
- SharedState gains `unique_count: int`
- WebSocket payload extends to `{"count": N, "unique_count": M}`
- No other components need to change

---

## Dependencies

```
fastapi
uvicorn[standard]
opencv-python-headless
ultralytics
psutil
python-multipart
```
