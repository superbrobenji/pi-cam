# Resource Exhaustion Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate memory/CPU leaks causing the Pi 5 to become unresponsive — fix zombie MJPEG generators, skip JPEG encoding when nobody is watching, release YOLO tensors promptly, add exponential backoff on camera failure, and expose CPU temperature + disk usage.

**Architecture:** Four targeted changes to existing files: `shared_state.py` gains four new fields; `health.py` gains temperature and disk polling; `detector.py` skips JPEG encoding when `stream_active=False` and adds tensor cleanup + retry backoff; `main.py` replaces the MJPEG generator with a disconnect-aware version protected by a 1-viewer lock.

**Tech Stack:** Python 3.11, FastAPI, Starlette, psutil, OpenCV, asyncio

---

## File Map

| File | Action | What changes |
|---|---|---|
| `shared_state.py` | Modify | Add `stream_active`, `cpu_temp`, `disk_used`, `disk_total` fields |
| `health.py` | Modify | Add `_read_cpu_temp()`, disk polling via psutil |
| `detector.py` | Modify | Conditional JPEG encoding, `del results`, exponential backoff |
| `main.py` | Modify | Disconnect-aware MJPEG generator, `_stream_lock`, 409 on second viewer |
| `tests/test_shared_state.py` | Modify | Add assertions for new fields |
| `tests/test_health.py` | Modify | Add assertions for disk + temp fields |
| `tests/test_detector.py` | Modify | Update frame test to set `stream_active=True` |
| `tests/test_integration.py` | Modify | Update fixture signature, add 409 test, update health key/type assertions |

---

### Task 1: Extend SharedState with new fields

**Files:**
- Modify: `shared_state.py`
- Test: `tests/test_shared_state.py`

- [ ] **Step 1: Write failing tests for new fields**

Replace the entire `test_initial_values` function in `tests/test_shared_state.py`:

```python
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
    assert snap["stream_active"] is False
    assert snap["cpu_temp"] is None
    assert snap["disk_used"] == 0
    assert snap["disk_total"] == 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
python3 -m pytest tests/test_shared_state.py::test_initial_values -v
```

Expected: FAIL — `KeyError: 'stream_active'`

- [ ] **Step 3: Update `shared_state.py`**

Replace the entire file:

```python
import threading

_FIELDS = frozenset({
    "count", "frame", "camera_ok", "model_ok",
    "ws_clients", "cpu_percent", "ram_used", "ram_total",
    "stream_active", "cpu_temp", "disk_used", "disk_total",
})


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
        self.stream_active = False
        self.cpu_temp = None
        self.disk_used = 0
        self.disk_total = 0

    def update(self, **kwargs):
        unknown = kwargs.keys() - _FIELDS
        if unknown:
            raise KeyError(f"Unknown SharedState fields: {unknown}")
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
                "stream_active": self.stream_active,
                "cpu_temp": self.cpu_temp,
                "disk_used": self.disk_used,
                "disk_total": self.disk_total,
            }

    def get_frame(self) -> bytes:
        with self._lock:
            return self.frame
```

- [ ] **Step 4: Run all SharedState tests**

```bash
python3 -m pytest tests/test_shared_state.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add shared_state.py tests/test_shared_state.py
git commit -m "feat: add stream_active, cpu_temp, disk fields to SharedState"
```

---

### Task 2: Fix health poller — temperature + disk

**Files:**
- Modify: `health.py`
- Test: `tests/test_health.py`

- [ ] **Step 1: Write failing tests**

Replace the entire `tests/test_health.py`:

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
    assert snap["disk_total"] > 0
    assert snap["disk_used"] >= 0
    assert snap["disk_used"] <= snap["disk_total"]
    assert snap["cpu_temp"] is None or isinstance(snap["cpu_temp"], float)
```

- [ ] **Step 2: Run to verify it fails**

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: FAIL — `AssertionError` on `disk_total > 0` (field not yet populated)

- [ ] **Step 3: Update `health.py`**

Replace the entire file:

```python
import time
import psutil
from shared_state import SharedState


def _read_cpu_temp() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return None


def run_health_poller(state: SharedState, interval: float = 2.0) -> None:
    while True:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        state.update(
            cpu_percent=float(cpu),
            ram_used=mem.used,
            ram_total=mem.total,
            cpu_temp=_read_cpu_temp(),
            disk_used=disk.used,
            disk_total=disk.total,
        )
        time.sleep(interval)
```

- [ ] **Step 4: Run health tests**

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add health.py tests/test_health.py
git commit -m "feat: add cpu temperature and disk usage to health poller"
```

---

### Task 3: Fix detector — conditional JPEG, tensor cleanup, retry backoff

**Files:**
- Modify: `detector.py`
- Test: `tests/test_detector.py`

- [ ] **Step 1: Write failing test for conditional JPEG**

Add two tests to `tests/test_detector.py` — append after the existing tests:

```python
def test_mock_frame_empty_when_stream_inactive():
    state = SharedState()
    # stream_active defaults to False — no frame should be encoded
    _start_detector(state)
    assert state.get_frame() == b""


def test_mock_frame_nonempty_when_stream_active():
    state = SharedState()
    state.update(stream_active=True)
    _start_detector(state)
    frame = state.get_frame()
    assert isinstance(frame, bytes)
    assert len(frame) > 0
```

Also update the existing `test_mock_frame_is_nonempty_bytes` to match new behaviour (it previously assumed frame was always populated):

```python
def test_mock_frame_is_nonempty_bytes():
    state = SharedState()
    state.update(stream_active=True)
    _start_detector(state)
    frame = state.get_frame()
    assert isinstance(frame, bytes)
    assert len(frame) > 0
```

- [ ] **Step 2: Run to verify new tests fail, existing pass**

```bash
python3 -m pytest tests/test_detector.py -v
```

Expected:
- `test_mock_frame_is_nonempty_bytes` — PASS (stream_active=True set, old detector still encodes)
- `test_mock_frame_empty_when_stream_inactive` — FAIL (frame is non-empty, should be empty)
- `test_mock_frame_nonempty_when_stream_active` — PASS (coincidentally, until we change detector)

- [ ] **Step 3: Update `detector.py`**

Replace the entire file:

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
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("JPEG encode failed")
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
        if state.stream_active:
            state.update(frame=_encode_jpeg(_MOCK_FRAME))
        state.update(camera_ok=True, count=0)
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
    retry_delay = 2.0
    while True:
        t0 = time.monotonic()
        try:
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)

            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Frame read failed")

            retry_delay = 2.0

            if state.stream_active:
                state.update(frame=_encode_jpeg(frame))
            state.update(camera_ok=True)

            results = model(frame, verbose=False)[0]
            count = sum(
                1
                for box in results.boxes
                if int(box.cls[0]) == _PERSON_CLASS_ID
                and float(box.conf[0]) >= _CONFIDENCE_THRESHOLD
            )
            del results
            state.update(count=count)

        except Exception:
            state.update(camera_ok=False, count=0)
            if cap is not None:
                cap.release()
                cap = None
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30.0)
            continue

        time.sleep(max(0.0, 1.0 - (time.monotonic() - t0)))
```

- [ ] **Step 4: Run all detector tests**

```bash
python3 -m pytest tests/test_detector.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add detector.py tests/test_detector.py
git commit -m "fix: skip JPEG encoding when stream inactive, del results, exponential backoff"
```

---

### Task 4: Fix MJPEG stream — disconnect detection, 1-viewer lock, 409

**Files:**
- Modify: `main.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write failing tests**

Replace the entire `tests/test_integration.py`:

```python
import pytest
import main as _main_module
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_stream_lock(monkeypatch):
    """Ensure _stream_lock is free before and after each test."""
    if _main_module._stream_lock.locked():
        _main_module._stream_lock.release()
    yield
    if _main_module._stream_lock.locked():
        _main_module._stream_lock.release()


@pytest.fixture()
def _finite_stream(monkeypatch):
    """Replace _mjpeg_generator with a finite version that accepts a request arg."""
    _FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

    async def _finite(request):
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        for _ in range(3):
            yield boundary + _FAKE_JPEG + b"\r\n"

    monkeypatch.setattr(_main_module, "_mjpeg_generator", _finite)


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_expected_keys(client):
    data = client.get("/health").json()
    expected = {
        "count", "camera_ok", "model_ok", "ws_clients",
        "cpu_percent", "ram_used", "ram_total",
        "stream_active", "cpu_temp", "disk_used", "disk_total",
    }
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
    assert isinstance(data["stream_active"], bool)
    assert data["cpu_temp"] is None or isinstance(data["cpu_temp"], float)
    assert isinstance(data["disk_used"], int)
    assert isinstance(data["disk_total"], int)


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


def test_stream_content_type(client, _finite_stream):
    with client.stream("GET", "/stream") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers["content-type"]


def test_stream_rejects_second_viewer(monkeypatch):
    class _LockedMock:
        def locked(self):
            return True

    monkeypatch.setattr(_main_module, "_stream_lock", _LockedMock())
    with TestClient(app) as c:
        response = c.get("/stream")
    assert response.status_code == 409
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m pytest tests/test_integration.py -v
```

Expected failures:
- `test_health_returns_expected_keys` — FAIL missing `stream_active`, `cpu_temp`, `disk_used`, `disk_total`
- `test_health_value_types` — FAIL on same missing keys
- `test_stream_rejects_second_viewer` — FAIL (no 409 behaviour yet)
- `test_stream_content_type` — FAIL (`_finite` now takes `request` but old generator takes none)

- [ ] **Step 3: Update `main.py`**

Replace the entire file:

```python
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from shared_state import SharedState
from detector import run_detector
from health import run_health_poller

state = SharedState()
ws_clients: set[WebSocket] = set()
_ws_lock = asyncio.Lock()
_stream_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=run_detector, args=(state,), daemon=True).start()
    threading.Thread(target=run_health_poller, args=(state,), daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(state.snapshot())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    async with _ws_lock:
        ws_clients.add(websocket)
        state.update(ws_clients=len(ws_clients))
    try:
        while True:
            await websocket.send_json({"count": state.count})
            await asyncio.sleep(1.0)
    except Exception:
        pass
    finally:
        async with _ws_lock:
            ws_clients.discard(websocket)
            state.update(ws_clients=len(ws_clients))


async def _mjpeg_generator(request: Request):
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    state.update(stream_active=True)
    try:
        while not await request.is_disconnected():
            frame = state.get_frame()
            if frame:
                yield boundary + frame + b"\r\n"
            await asyncio.sleep(0.1)
    finally:
        state.update(stream_active=False)


@app.get("/stream")
async def stream(request: Request) -> Response:
    if _stream_lock.locked():
        return Response(status_code=409, content="Stream already active")
    await _stream_lock.acquire()

    async def locked_generator():
        try:
            async for chunk in _mjpeg_generator(request):
                yield chunk
        finally:
            _stream_lock.release()

    return StreamingResponse(
        locked_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
```

- [ ] **Step 4: Run all integration tests**

```bash
python3 -m pytest tests/test_integration.py -v
```

Expected: all PASS

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest -v
```

Expected: all 20 tests PASS (17 existing + 2 new detector tests + 1 new integration test)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "fix: disconnect-aware MJPEG generator with 1-viewer lock and 409 response"
```
