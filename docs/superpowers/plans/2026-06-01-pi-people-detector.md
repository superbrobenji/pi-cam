# Pi People Detector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI service for Raspberry Pi 5 that detects people via YOLOv8, streams live count over WebSocket, and serves a web UI with device health stats and MJPEG camera preview.

**Architecture:** Single FastAPI process with two daemon threads (detector, health poller) writing into a thread-safe SharedState object. FastAPI exposes WebSocket for count push, MJPEG stream for preview, JSON health endpoint, and serves a vanilla JS UI. `MOCK_CAMERA=1` env var bypasses hardware for dev/CI.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, OpenCV (headless), YOLOv8 (ultralytics), psutil, pytest, httpx

---

## File Map

| File | Responsibility |
|---|---|
| `shared_state.py` | Thread-safe container for all shared runtime state |
| `health.py` | Daemon thread — polls psutil every 2s, writes to SharedState |
| `detector.py` | Daemon thread — YOLO detection loop, writes count/frame to SharedState |
| `main.py` | FastAPI app — wires threads, exposes all endpoints |
| `static/index.html` | Vanilla JS UI — count display, health panel, camera preview toggle |
| `requirements.txt` | Pinned dependencies |
| `tests/conftest.py` | Sets `MOCK_CAMERA=1` before any module import |
| `tests/test_shared_state.py` | Unit tests for SharedState |
| `tests/test_health.py` | Unit tests for health poller |
| `tests/test_detector.py` | Unit tests for detector (mock mode) |
| `tests/test_integration.py` | Integration tests for all FastAPI endpoints |

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `static/` directory

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
opencv-python-headless>=4.9.0
ultralytics>=8.2.0
psutil>=5.9.0
python-multipart>=0.0.9
httpx>=0.27.0
pytest>=8.0.0
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import os
os.environ["MOCK_CAMERA"] = "1"
```

This file is auto-loaded by pytest before any test module is imported, ensuring `MOCK_CAMERA=1` is set before `detector.py` or `main.py` are imported.

- [ ] **Step 3: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 4: Create static directory**

```bash
mkdir -p static
touch static/.gitkeep
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error. On a non-Pi dev machine, `ultralytics` pulls in a CPU-only torch wheel (~700MB) — this is expected and correct.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/ static/
git commit -m "chore: project scaffold with dependencies"
```

---

### Task 2: SharedState

**Files:**
- Create: `shared_state.py`
- Create: `tests/test_shared_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_shared_state.py`:

```python
import threading
from shared_state import SharedState


def test_initial_values():
    state = SharedState()
    snap = state.snapshot()
    assert snap["count"] == 0
    assert snap["camera_ok"] is False
    assert snap["model_ok"] is False
    assert snap["ws_clients"] == 0
    assert snap["cpu_percent"] == 0.0
    assert snap["ram_used"] == 0
    assert snap["ram_total"] == 0


def test_update_and_snapshot():
    state = SharedState()
    state.update(count=3, camera_ok=True)
    snap = state.snapshot()
    assert snap["count"] == 3
    assert snap["camera_ok"] is True


def test_update_does_not_leak_frame_into_snapshot():
    state = SharedState()
    state.update(frame=b"testdata")
    snap = state.snapshot()
    assert "frame" not in snap


def test_get_frame_returns_bytes():
    state = SharedState()
    state.update(frame=b"testdata")
    assert state.get_frame() == b"testdata"


def test_thread_safe_concurrent_updates():
    state = SharedState()
    errors = []

    def writer(val):
        for _ in range(200):
            try:
                state.update(count=val)
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert isinstance(state.snapshot()["count"], int)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_shared_state.py -v
```

Expected: `ModuleNotFoundError: No module named 'shared_state'`

- [ ] **Step 3: Implement `shared_state.py`**

```python
import threading


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self.count = 0
        self.frame = b""
        self.camera_ok = False
        self.model_ok = False
        self.ws_clients = 0
        self.cpu_percent = 0.0
        self.ram_used = 0
        self.ram_total = 0

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "count": self.count,
                "camera_ok": self.camera_ok,
                "model_ok": self.model_ok,
                "ws_clients": self.ws_clients,
                "cpu_percent": self.cpu_percent,
                "ram_used": self.ram_used,
                "ram_total": self.ram_total,
            }

    def get_frame(self) -> bytes:
        with self._lock:
            return self.frame
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_shared_state.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add shared_state.py tests/test_shared_state.py
git commit -m "feat: thread-safe SharedState container"
```

---

### Task 3: Health Poller

**Files:**
- Create: `health.py`
- Create: `tests/test_health.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_health.py`:

```python
import time
import threading
from shared_state import SharedState
from health import run_health_poller


def test_health_poller_updates_cpu_and_ram():
    state = SharedState()
    t = threading.Thread(target=run_health_poller, args=(state, 0.05), daemon=True)
    t.start()
    time.sleep(0.25)
    snap = state.snapshot()
    assert isinstance(snap["cpu_percent"], float)
    assert snap["ram_used"] > 0
    assert snap["ram_total"] > 0
    assert snap["ram_used"] <= snap["ram_total"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_health.py -v
```

Expected: `ModuleNotFoundError: No module named 'health'`

- [ ] **Step 3: Implement `health.py`**

```python
import time
import psutil
from shared_state import SharedState


def run_health_poller(state: SharedState, interval: float = 2.0) -> None:
    while True:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        state.update(
            cpu_percent=float(cpu),
            ram_used=mem.used,
            ram_total=mem.total,
        )
        time.sleep(interval)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_health.py -v
```

Expected: 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add health.py tests/test_health.py
git commit -m "feat: health poller thread using psutil"
```

---

### Task 4: Detector

**Files:**
- Create: `detector.py`
- Create: `tests/test_detector.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_detector.py`:

```python
import time
import threading
from shared_state import SharedState
from detector import run_detector


def _start_detector(state: SharedState) -> None:
    threading.Thread(target=run_detector, args=(state,), daemon=True).start()
    time.sleep(0.3)


def test_mock_sets_camera_ok():
    state = SharedState()
    _start_detector(state)
    assert state.camera_ok is True


def test_mock_sets_model_ok():
    state = SharedState()
    _start_detector(state)
    assert state.model_ok is True


def test_mock_count_is_int():
    state = SharedState()
    _start_detector(state)
    assert isinstance(state.count, int)


def test_mock_frame_is_nonempty_bytes():
    state = SharedState()
    _start_detector(state)
    frame = state.get_frame()
    assert isinstance(frame, bytes)
    assert len(frame) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_detector.py -v
```

Expected: `ModuleNotFoundError: No module named 'detector'`

- [ ] **Step 3: Implement `detector.py`**

```python
import os
import time
import cv2
import numpy as np
from shared_state import SharedState

_MOCK_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
_CONFIDENCE_THRESHOLD = 0.5
_PERSON_CLASS_ID = 0


def _encode_jpeg(frame: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()


def run_detector(state: SharedState) -> None:
    if os.environ.get("MOCK_CAMERA") == "1":
        state.update(model_ok=True)
        _run_mock_loop(state)
    else:
        _run_live_loop(state)


def _run_mock_loop(state: SharedState) -> None:
    while True:
        t0 = time.monotonic()
        state.update(
            frame=_encode_jpeg(_MOCK_FRAME),
            camera_ok=True,
            count=0,
        )
        time.sleep(max(0.0, 1.0 - (time.monotonic() - t0)))


def _run_live_loop(state: SharedState) -> None:
    from ultralytics import YOLO

    try:
        model = YOLO("yolov8n.pt")
        state.update(model_ok=True)
    except Exception:
        state.update(model_ok=False)
        return

    cap = None
    while True:
        t0 = time.monotonic()
        try:
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)

            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Frame read failed")

            state.update(frame=_encode_jpeg(frame), camera_ok=True)

            results = model(frame, verbose=False)[0]
            count = sum(
                1
                for box in results.boxes
                if int(box.cls[0]) == _PERSON_CLASS_ID
                and float(box.conf[0]) >= _CONFIDENCE_THRESHOLD
            )
            state.update(count=count)

        except Exception:
            state.update(camera_ok=False, count=0)
            if cap is not None:
                cap.release()
                cap = None
            time.sleep(2.0)
            continue

        time.sleep(max(0.0, 1.0 - (time.monotonic() - t0)))
```

Note: `from ultralytics import YOLO` is inside `_run_live_loop` so mock mode never imports torch, keeping tests fast.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_detector.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add detector.py tests/test_detector.py
git commit -m "feat: YOLO detector thread with MOCK_CAMERA support"
```

---

### Task 5: FastAPI — Health Endpoint

**Files:**
- Create: `main.py`
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_integration.py`:

```python
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_expected_keys(client):
    data = client.get("/health").json()
    expected = {"count", "camera_ok", "model_ok", "ws_clients", "cpu_percent", "ram_used", "ram_total"}
    assert expected.issubset(data.keys())


def test_health_value_types(client):
    data = client.get("/health").json()
    assert isinstance(data["count"], int)
    assert isinstance(data["camera_ok"], bool)
    assert isinstance(data["model_ok"], bool)
    assert isinstance(data["ws_clients"], int)
    assert isinstance(data["cpu_percent"], float)
    assert isinstance(data["ram_used"], int)
    assert isinstance(data["ram_total"], int)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_integration.py::test_health_returns_200 -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Implement `main.py`**

```python
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from shared_state import SharedState
from detector import run_detector
from health import run_health_poller

state = SharedState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=run_detector, args=(state,), daemon=True).start()
    threading.Thread(target=run_health_poller, args=(state,), daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(state.snapshot())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_integration.py::test_health_returns_200 tests/test_integration.py::test_health_returns_expected_keys tests/test_integration.py::test_health_value_types -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "feat: FastAPI app with /health endpoint"
```

---

### Task 6: FastAPI — WebSocket Endpoint

**Files:**
- Modify: `main.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add failing WebSocket tests**

Append to `tests/test_integration.py`:

```python
def test_websocket_emits_count(client):
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "count" in data
        assert isinstance(data["count"], int)


def test_websocket_increments_ws_clients(client):
    before = client.get("/health").json()["ws_clients"]
    with client.websocket_connect("/ws"):
        during = client.get("/health").json()["ws_clients"]
    assert during >= before + 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_integration.py::test_websocket_emits_count -v
```

Expected: FAIL — no `/ws` route.

- [ ] **Step 3: Add WebSocket endpoint to `main.py`**

Add these imports at the top of `main.py`, after the existing imports:

```python
import asyncio
from fastapi import WebSocket

ws_clients: set[WebSocket] = set()
```

Add this endpoint after the `health` function:

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    ws_clients.add(websocket)
    state.update(ws_clients=len(ws_clients))
    try:
        while True:
            await websocket.send_json({"count": state.count})
            await asyncio.sleep(1.0)
    except Exception:
        pass
    finally:
        ws_clients.discard(websocket)
        state.update(ws_clients=len(ws_clients))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_integration.py::test_websocket_emits_count tests/test_integration.py::test_websocket_increments_ws_clients -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "feat: WebSocket endpoint broadcasting people count every 1s"
```

---

### Task 7: FastAPI — MJPEG Stream Endpoint

**Files:**
- Modify: `main.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add failing stream test**

Append to `tests/test_integration.py`:

```python
def test_stream_content_type(client):
    with client.stream("GET", "/stream") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_integration.py::test_stream_content_type -v
```

Expected: FAIL — no `/stream` route.

- [ ] **Step 3: Add stream endpoint to `main.py`**

Add this import at the top of `main.py`, after existing imports:

```python
from fastapi.responses import StreamingResponse
```

Add this function and endpoint after the WebSocket endpoint:

```python
async def _mjpeg_generator():
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        frame = state.get_frame()
        if frame:
            yield boundary + frame + b"\r\n"
        await asyncio.sleep(0.1)


@app.get("/stream")
async def stream() -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "feat: MJPEG stream endpoint for camera preview"
```

---

### Task 8: Web UI + Static Serving

**Files:**
- Modify: `main.py`
- Create: `static/index.html`

- [ ] **Step 1: Add static file serving to `main.py`**

Add this import at the top of `main.py`:

```python
from fastapi.staticfiles import StaticFiles
```

Add these two lines immediately after `app = FastAPI(lifespan=lifespan)`:

```python
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")
```

- [ ] **Step 2: Create `static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pi People Counter</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: monospace; background: #0d0d0d; color: #e0e0e0; padding: 2rem; }
        h1 { text-align: center; margin-bottom: 2rem; letter-spacing: 0.2em; font-size: 1.2rem; color: #888; }
        .count-panel { text-align: center; margin-bottom: 2rem; }
        .count-label { font-size: 0.9rem; color: #666; letter-spacing: 0.15em; margin-bottom: 0.5rem; }
        .count-value { font-size: 6rem; font-weight: bold; color: #fff; line-height: 1; }
        .main-grid { display: grid; grid-template-columns: 200px 1fr; gap: 1.5rem; }
        .health-panel h2 { font-size: 0.8rem; color: #666; letter-spacing: 0.1em; margin-bottom: 1rem; }
        .health-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; font-size: 0.85rem; }
        .health-label { color: #888; }
        .health-value { color: #ccc; }
        .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .dot.ok { background: #4caf50; }
        .dot.err { background: #f44336; }
        .preview-toggle { background: #1e1e1e; border: 1px solid #333; color: #ccc; padding: 0.5rem 1rem; cursor: pointer; font-family: monospace; font-size: 0.85rem; margin-bottom: 0.75rem; display: block; }
        .preview-toggle:hover { background: #2a2a2a; }
        #camera-img { width: 100%; max-width: 640px; display: block; border: 1px solid #333; }
    </style>
</head>
<body>
    <h1>PI PEOPLE COUNTER</h1>
    <div class="count-panel">
        <div class="count-label">PEOPLE IN FRAME</div>
        <div class="count-value" id="count">—</div>
    </div>
    <div class="main-grid">
        <div class="health-panel">
            <h2>HEALTH</h2>
            <div class="health-row">
                <span class="health-label">CPU</span>
                <span class="health-value" id="cpu">—</span>
            </div>
            <div class="health-row">
                <span class="health-label">RAM</span>
                <span class="health-value" id="ram">—</span>
            </div>
            <div class="health-row">
                <span class="health-label">Camera</span>
                <span id="camera-dot" class="dot err"></span>
            </div>
            <div class="health-row">
                <span class="health-label">YOLOv8</span>
                <span id="yolo-dot" class="dot err"></span>
            </div>
            <div class="health-row">
                <span class="health-label">WebSocket</span>
                <span id="ws-dot" class="dot err"></span>
            </div>
        </div>
        <div class="preview-panel">
            <button class="preview-toggle" id="preview-btn" onclick="togglePreview()">Open Camera Preview</button>
            <img id="camera-img" alt="Camera preview" style="display:none;" />
        </div>
    </div>
    <script>
        let wsRetryDelay = 1000;
        const wsRetryMax = 30000;

        function connectWS() {
            const ws = new WebSocket(`ws://${location.host}/ws`);
            ws.onopen = () => {
                document.getElementById('ws-dot').className = 'dot ok';
                wsRetryDelay = 1000;
            };
            ws.onmessage = (e) => {
                const data = JSON.parse(e.data);
                document.getElementById('count').textContent = data.count;
            };
            ws.onclose = ws.onerror = () => {
                document.getElementById('ws-dot').className = 'dot err';
                setTimeout(connectWS, wsRetryDelay);
                wsRetryDelay = Math.min(wsRetryDelay * 2, wsRetryMax);
            };
        }

        function pollHealth() {
            fetch('/health')
                .then(r => r.json())
                .then(d => {
                    document.getElementById('cpu').textContent = d.cpu_percent.toFixed(1) + '%';
                    const ramPct = ((d.ram_used / d.ram_total) * 100).toFixed(1);
                    document.getElementById('ram').textContent = ramPct + '%';
                    document.getElementById('camera-dot').className = 'dot ' + (d.camera_ok ? 'ok' : 'err');
                    document.getElementById('yolo-dot').className = 'dot ' + (d.model_ok ? 'ok' : 'err');
                })
                .catch(() => {});
        }

        function togglePreview() {
            const img = document.getElementById('camera-img');
            const btn = document.getElementById('preview-btn');
            const opening = img.style.display === 'none';
            if (opening) {
                img.src = '/stream';
                img.style.display = 'block';
                btn.textContent = 'Close Camera Preview';
            } else {
                img.src = '';
                img.style.display = 'none';
                btn.textContent = 'Open Camera Preview';
            }
        }

        connectWS();
        pollHealth();
        setInterval(pollHealth, 3000);
    </script>
</body>
</html>
```

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Manual smoke test**

```bash
MOCK_CAMERA=1 uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000`. Verify:
- Count shows `0`
- CPU % and RAM % update every 3s
- Camera dot green, YOLOv8 dot green, WebSocket dot green
- Camera preview toggle opens a black frame (mock), close button stops the stream

- [ ] **Step 5: Commit**

```bash
git add main.py static/index.html
git commit -m "feat: web UI with health stats and MJPEG camera preview toggle"
```

---

### Task 9: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# Pi People Detector

Detects people in a webcam frame using YOLOv8 and broadcasts a live count over WebSocket. Includes a web UI with device health stats and optional MJPEG camera preview.

## Requirements

- Python 3.11+
- Raspberry Pi 5 (or any Linux/macOS machine for dev)
- USB webcam (for live mode)

## Setup

pip install -r requirements.txt

## Running

### On the Pi (live camera)

uvicorn main:app --host 0.0.0.0 --port 8000

Open `http://<pi-ip>:8000` in a browser on your local network.

### Development (no camera)

MOCK_CAMERA=1 uvicorn main:app --reload --port 8000

### Tests

pytest -v

## WebSocket API

Connect to `ws://<host>:8000/ws`. Receives JSON every ~1 second:

{"count": 3}

## Endpoints

| Path | Description |
|---|---|
| `GET /` | Web UI |
| `WS /ws` | Live people count |
| `GET /stream` | MJPEG camera preview |
| `GET /health` | JSON device health snapshot |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage"
```
