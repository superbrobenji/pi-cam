# Management Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate sidecar monitoring process on port 8001 that survives main app crashes, shows per-component errors + log trails, and provides restart controls for individual components and the whole service.

**Architecture:** `log_buffer.py` provides a thread-safe in-memory ring buffer per component. `shared_state.py` gains 8 error-tracking fields. `detector.py` and `health.py` gain stop events for graceful restart and write errors to the log buffer. `main.py` gains `/control/restart/{component}` and `/logs/{component}` endpoints. A new `monitor.py` FastAPI process on port 8001 polls the main app, caches state, and serves the two-tab dashboard from `monitor_static/index.html`.

**Tech Stack:** Python 3.9+, FastAPI, httpx, asyncio, threading, systemd, vanilla JS

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `log_buffer.py` | Create | Thread-safe ring buffer, 100 entries per component |
| `shared_state.py` | Modify | Add 8 error fields (camera/model/health/stream error + timestamp) |
| `detector.py` | Modify | Accept stop_event, write errors to log_buffer, track camera/model errors in state |
| `health.py` | Modify | Accept stop_event, write errors to log_buffer, track health errors in state |
| `main.py` | Modify | Module-level stop events, restart endpoints, /logs endpoint, stream error tracking |
| `monitor.py` | Create | Sidecar FastAPI on port 8001: poll, proxy, serve dashboard |
| `monitor_static/index.html` | Create | Two-tab dashboard UI (OPS + LIVE) |
| `install.sh` | Modify | Add pi-monitor.service |
| `tests/test_log_buffer.py` | Create | Tests for log_buffer module |
| `tests/test_shared_state.py` | Modify | Add assertions for 8 new error fields |
| `tests/test_detector.py` | Modify | Pass stop_event; test error field population |
| `tests/test_health.py` | Modify | Pass stop_event; test health error field |
| `tests/test_integration.py` | Modify | Test restart + logs endpoints, new health keys |
| `tests/test_monitor.py` | Create | Test monitor status, restart, log proxy endpoints |

---

### Task 1: Create `log_buffer.py`

**Files:**
- Create: `log_buffer.py`
- Create: `tests/test_log_buffer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_log_buffer.py`:

```python
import threading
import log_buffer


def test_get_empty_initially():
    log_buffer._buffers["detector"].clear()
    assert log_buffer.get("detector") == []


def test_append_and_get():
    log_buffer._buffers["detector"].clear()
    log_buffer.append("detector", "ERROR", "camera failed")
    entries = log_buffer.get("detector")
    assert len(entries) == 1
    assert entries[0]["level"] == "ERROR"
    assert entries[0]["msg"] == "camera failed"
    assert isinstance(entries[0]["ts"], float)


def test_get_returns_copy():
    log_buffer._buffers["detector"].clear()
    log_buffer.append("detector", "INFO", "test")
    result = log_buffer.get("detector")
    result.clear()
    assert len(log_buffer.get("detector")) == 1


def test_max_100_entries():
    log_buffer._buffers["health"].clear()
    for i in range(110):
        log_buffer.append("health", "INFO", f"msg {i}")
    assert len(log_buffer.get("health")) == 100


def test_thread_safe_concurrent_appends():
    log_buffer._buffers["stream"].clear()
    errors = []

    def writer():
        for _ in range(50):
            try:
                log_buffer.append("stream", "INFO", "msg")
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(log_buffer.get("stream")) <= 100
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_log_buffer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'log_buffer'`

- [ ] **Step 3: Create `log_buffer.py`**

```python
import threading
import time
from collections import deque
from typing import Any, Dict, List

COMPONENTS = ("detector", "health", "stream")

_buffers: Dict[str, deque] = {c: deque(maxlen=100) for c in COMPONENTS}
_lock = threading.Lock()


def append(component: str, level: str, msg: str) -> None:
    with _lock:
        _buffers[component].append({"ts": time.time(), "level": level, "msg": msg})


def get(component: str) -> List[Dict[str, Any]]:
    with _lock:
        return list(_buffers[component])
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_log_buffer.py -v
```

Expected: all 5 PASS

- [ ] **Step 5: Run full suite to check no regressions**

```bash
python3 -m pytest -v
```

Expected: all 20 PASS

- [ ] **Step 6: Commit**

```bash
git add log_buffer.py tests/test_log_buffer.py
git commit -m "feat: add thread-safe log ring buffer per component"
```

---

### Task 2: Extend SharedState with 8 error fields

**Files:**
- Modify: `shared_state.py`
- Modify: `tests/test_shared_state.py`

- [ ] **Step 1: Write failing test**

Replace `test_initial_values` in `tests/test_shared_state.py`:

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
    assert snap["camera_error"] is None
    assert snap["camera_error_at"] is None
    assert snap["model_error"] is None
    assert snap["model_error_at"] is None
    assert snap["health_error"] is None
    assert snap["health_error_at"] is None
    assert snap["stream_error"] is None
    assert snap["stream_error_at"] is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_shared_state.py::test_initial_values -v
```

Expected: FAIL — `KeyError: 'camera_error'`

- [ ] **Step 3: Update `shared_state.py`**

Replace the entire file:

```python
import threading
from typing import Optional

_FIELDS = frozenset({
    "count", "frame", "camera_ok", "model_ok",
    "ws_clients", "cpu_percent", "ram_used", "ram_total",
    "stream_active", "cpu_temp", "disk_used", "disk_total",
    "camera_error", "camera_error_at",
    "model_error", "model_error_at",
    "health_error", "health_error_at",
    "stream_error", "stream_error_at",
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
        self.cpu_temp: Optional[float] = None
        self.disk_used = 0
        self.disk_total = 0
        self.camera_error: Optional[str] = None
        self.camera_error_at: Optional[float] = None
        self.model_error: Optional[str] = None
        self.model_error_at: Optional[float] = None
        self.health_error: Optional[str] = None
        self.health_error_at: Optional[float] = None
        self.stream_error: Optional[str] = None
        self.stream_error_at: Optional[float] = None

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
                "camera_error": self.camera_error,
                "camera_error_at": self.camera_error_at,
                "model_error": self.model_error,
                "model_error_at": self.model_error_at,
                "health_error": self.health_error,
                "health_error_at": self.health_error_at,
                "stream_error": self.stream_error,
                "stream_error_at": self.stream_error_at,
            }

    def get_frame(self) -> bytes:
        with self._lock:
            return self.frame
```

- [ ] **Step 4: Run all SharedState tests**

```bash
python3 -m pytest tests/test_shared_state.py -v
```

Expected: all 6 PASS

- [ ] **Step 5: Commit**

```bash
git add shared_state.py tests/test_shared_state.py
git commit -m "feat: add per-component error fields to SharedState"
```

---

### Task 3: Update `detector.py` — stop event + error tracking

**Files:**
- Modify: `detector.py`
- Modify: `tests/test_detector.py`

- [ ] **Step 1: Write failing tests**

Add to the bottom of `tests/test_detector.py`:

```python
import threading


def test_detector_stops_when_stop_event_set():
    state = SharedState()
    stop = threading.Event()
    t = threading.Thread(target=run_detector, args=(state, stop), daemon=True)
    t.start()
    time.sleep(0.4)
    stop.set()
    t.join(timeout=3.0)
    assert not t.is_alive(), "Detector thread should have exited after stop_event set"
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_detector.py::test_detector_stops_when_stop_event_set -v
```

Expected: FAIL — `run_detector() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Update `detector.py`**

Replace the entire file:

```python
import os
import time
import threading
import cv2
import numpy as np
from typing import Optional
import log_buffer
from shared_state import SharedState

_MOCK_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
_CONFIDENCE_THRESHOLD = 0.5
_PERSON_CLASS_ID = 0


def _encode_jpeg(frame: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def run_detector(state: SharedState, stop_event: Optional[threading.Event] = None) -> None:
    if stop_event is None:
        stop_event = threading.Event()
    if os.environ.get("MOCK_CAMERA") == "1":
        state.update(model_ok=True)
        _run_mock_loop(state, stop_event)
    else:
        _run_live_loop(state, stop_event)


def _run_mock_loop(state: SharedState, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        t0 = time.monotonic()
        if state.stream_active:
            state.update(frame=_encode_jpeg(_MOCK_FRAME))
        state.update(camera_ok=True, count=0)
        stop_event.wait(max(0.0, 1.0 - (time.monotonic() - t0)))


def _run_live_loop(state: SharedState, stop_event: threading.Event) -> None:
    from ultralytics import YOLO

    try:
        model = YOLO("yolov8n.pt")
        state.update(model_ok=True, model_error=None, model_error_at=None)
    except Exception as e:
        msg = str(e)
        log_buffer.append("detector", "ERROR", f"Model load failed: {msg}")
        state.update(model_ok=False, model_error=msg, model_error_at=time.time())
        return

    cap = None
    retry_delay = 2.0
    while not stop_event.is_set():
        t0 = time.monotonic()
        try:
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)

            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Frame read failed")

            retry_delay = 2.0
            state.update(camera_ok=True, camera_error=None, camera_error_at=None)

            if state.stream_active:
                state.update(frame=_encode_jpeg(frame))

            results = model(frame, verbose=False)[0]
            count = sum(
                1
                for box in results.boxes
                if int(box.cls[0]) == _PERSON_CLASS_ID
                and float(box.conf[0]) >= _CONFIDENCE_THRESHOLD
            )
            del results
            state.update(count=count)

        except Exception as e:
            msg = str(e)
            log_buffer.append("detector", "ERROR", msg)
            state.update(
                camera_ok=False, count=0,
                camera_error=msg, camera_error_at=time.time(),
            )
            if cap is not None:
                cap.release()
                cap = None
            stop_event.wait(retry_delay)
            retry_delay = min(retry_delay * 2, 30.0)
            continue

        stop_event.wait(max(0.0, 1.0 - (time.monotonic() - t0)))
```

- [ ] **Step 4: Run all detector tests**

```bash
python3 -m pytest tests/test_detector.py -v
```

Expected: all 7 PASS (6 existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add detector.py tests/test_detector.py
git commit -m "feat: add stop_event and error tracking to detector"
```

---

### Task 4: Update `health.py` — stop event + error tracking

**Files:**
- Modify: `health.py`
- Modify: `tests/test_health.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_health.py`:

```python
def test_health_poller_stops_when_stop_event_set():
    state = SharedState()
    stop = threading.Event()
    t = threading.Thread(target=run_health_poller, args=(state, 0.05, stop), daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2.0)
    assert not t.is_alive(), "Health poller should have exited after stop_event set"


def test_health_poller_tracks_error_on_exception(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: (_ for _ in ()).throw(RuntimeError("psutil error")))
    state = SharedState()
    stop = threading.Event()
    t = threading.Thread(target=run_health_poller, args=(state, 0.05, stop), daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2.0)
    assert state.health_error == "psutil error"
    assert state.health_error_at is not None
```

Also add `import threading` to the imports at top of `tests/test_health.py` if not present.

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: FAIL — `run_health_poller() takes from 1 to 2 positional arguments but 3 were given` (or similar)

- [ ] **Step 3: Update `health.py`**

Replace the entire file:

```python
import time
import threading
import psutil
from typing import Optional
import log_buffer
from shared_state import SharedState


def _read_cpu_temp() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return None


def run_health_poller(
    state: SharedState,
    interval: float = 2.0,
    stop_event: Optional[threading.Event] = None,
) -> None:
    if stop_event is None:
        stop_event = threading.Event()
    while not stop_event.is_set():
        try:
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
                health_error=None,
                health_error_at=None,
            )
        except Exception as e:
            msg = str(e)
            log_buffer.append("health", "ERROR", msg)
            state.update(health_error=msg, health_error_at=time.time())
        stop_event.wait(interval)
```

- [ ] **Step 4: Run all health tests**

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add health.py tests/test_health.py
git commit -m "feat: add stop_event and error tracking to health poller"
```

---

### Task 5: Update `main.py` — stop events, restart endpoints, /logs endpoint

**Files:**
- Modify: `main.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_integration.py` (append after existing tests):

```python
def test_health_returns_error_fields(client):
    data = client.get("/health").json()
    for field in ("camera_error", "camera_error_at", "model_error", "model_error_at",
                  "health_error", "health_error_at", "stream_error", "stream_error_at"):
        assert field in data, f"Missing field: {field}"
        assert data[field] is None


def test_logs_returns_list_for_known_component(client):
    resp = client.get("/logs/detector")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_logs_returns_404_for_unknown_component(client):
    resp = client.get("/logs/unknown")
    assert resp.status_code == 404


def test_restart_detector_returns_restarting(client):
    resp = client.post("/control/restart/detector")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"


def test_restart_health_returns_restarting(client):
    resp = client.post("/control/restart/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m pytest tests/test_integration.py -v
```

Expected: 5 new tests FAIL (endpoints don't exist yet), existing 7 PASS

- [ ] **Step 3: Update `main.py`**

Replace the entire file:

```python
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import log_buffer
from shared_state import SharedState
from detector import run_detector
from health import run_health_poller

state = SharedState()
ws_clients: set[WebSocket] = set()
_ws_lock = asyncio.Lock()
_stream_lock = asyncio.Lock()

_detector_stop = threading.Event()
_health_stop = threading.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=run_detector, args=(state, _detector_stop), daemon=True).start()
    threading.Thread(target=run_health_poller, args=(state, 2.0, _health_stop), daemon=True).start()
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
    except Exception as e:
        msg = str(e)
        log_buffer.append("stream", "ERROR", msg)
        state.update(stream_error=msg, stream_error_at=asyncio.get_event_loop().time())
    finally:
        state.update(stream_active=False)


@app.get("/stream")
async def stream(request: Request) -> Response:
    # locked() check + acquire() is atomic in single-threaded asyncio (no await between them)
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


@app.post("/control/restart/detector")
async def restart_detector() -> JSONResponse:
    global _detector_stop
    _detector_stop.set()
    _detector_stop = threading.Event()
    log_buffer.append("detector", "INFO", "Restart requested via /control/restart/detector")
    threading.Thread(target=run_detector, args=(state, _detector_stop), daemon=True).start()
    return JSONResponse({"status": "restarting"})


@app.post("/control/restart/health")
async def restart_health() -> JSONResponse:
    global _health_stop
    _health_stop.set()
    _health_stop = threading.Event()
    log_buffer.append("health", "INFO", "Restart requested via /control/restart/health")
    threading.Thread(target=run_health_poller, args=(state, 2.0, _health_stop), daemon=True).start()
    return JSONResponse({"status": "restarting"})


@app.get("/logs/{component}")
async def get_logs(component: str) -> JSONResponse:
    if component not in log_buffer.COMPONENTS:
        return JSONResponse({"error": f"unknown component: {component}"}, status_code=404)
    return JSONResponse(log_buffer.get(component))
```

- [ ] **Step 4: Run all integration tests**

```bash
python3 -m pytest tests/test_integration.py -v
```

Expected: all 12 PASS

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -v
```

Expected: 33 PASS (20 prior + 5 log_buffer + 1 detector stop + 2 health stop/error + 5 new integration)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "feat: add restart endpoints, /logs endpoint, and stop events to main app"
```

---

### Task 6: Create `monitor.py`

**Files:**
- Create: `monitor.py`
- Create: `tests/test_monitor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_monitor.py`:

```python
import pytest
import monitor as _monitor_module
from fastapi.testclient import TestClient
from monitor import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_monitor_state():
    _monitor_module._state.app_online = False
    _monitor_module._state.last_health = {}
    _monitor_module._state.app_offline_since = None
    _monitor_module._state.last_poll_at = None
    yield


def test_status_has_required_keys(client):
    data = client.get("/api/status").json()
    assert "app_online" in data
    assert "app_offline_since" in data
    assert "last_poll_at" in data


def test_status_offline_by_default(client):
    data = client.get("/api/status").json()
    assert data["app_online"] is False


def test_status_reflects_cached_health(client):
    _monitor_module._state.app_online = True
    _monitor_module._state.last_health = {"count": 5, "camera_ok": True}
    data = client.get("/api/status").json()
    assert data["app_online"] is True
    assert data["count"] == 5
    assert data["camera_ok"] is True


def test_logs_returns_empty_list_when_offline(client):
    _monitor_module._state.app_online = False
    data = client.get("/api/logs/detector").json()
    assert data == []


def test_restart_component_returns_503_when_offline(client):
    _monitor_module._state.app_online = False
    resp = client.post("/api/restart/detector")
    assert resp.status_code == 503


def test_restart_service_calls_systemctl(client, monkeypatch):
    monkeypatch.setattr(
        _monitor_module.subprocess, "run",
        lambda *a, **kw: type("R", (), {"returncode": 0, "stderr": ""})(),
    )
    resp = client.post("/api/restart/service")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"


def test_restart_service_returns_500_on_failure(client, monkeypatch):
    monkeypatch.setattr(
        _monitor_module.subprocess, "run",
        lambda *a, **kw: type("R", (), {"returncode": 1, "stderr": "not allowed"})(),
    )
    resp = client.post("/api/restart/service")
    assert resp.status_code == 500
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_monitor.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'monitor'`

- [ ] **Step 3: Create `monitor.py`**

```python
import asyncio
import subprocess
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

MAIN_APP_URL = "http://localhost:8000"


@dataclass
class MonitorState:
    last_health: Dict[str, Any] = field(default_factory=dict)
    app_online: bool = False
    app_offline_since: Optional[float] = None
    last_poll_at: Optional[float] = None


_state = MonitorState()


async def _poll_main_app() -> None:
    async with httpx.AsyncClient(timeout=1.0) as client:
        while True:
            try:
                resp = await client.get(f"{MAIN_APP_URL}/health")
                resp.raise_for_status()
                _state.last_health = resp.json()
                _state.app_online = True
                _state.app_offline_since = None
            except Exception:
                if _state.app_online:
                    _state.app_offline_since = time.time()
                _state.app_online = False
            _state.last_poll_at = time.time()
            await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_poll_main_app())
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("monitor_static/index.html")


@app.get("/api/status")
async def status() -> JSONResponse:
    return JSONResponse({
        **_state.last_health,
        "app_online": _state.app_online,
        "app_offline_since": _state.app_offline_since,
        "last_poll_at": _state.last_poll_at,
    })


@app.get("/api/logs/{component}")
async def get_logs(component: str) -> JSONResponse:
    if not _state.app_online:
        return JSONResponse([])
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{MAIN_APP_URL}/logs/{component}")
            return JSONResponse(resp.json())
    except Exception:
        return JSONResponse([])


@app.post("/api/restart/detector")
async def restart_detector() -> JSONResponse:
    if not _state.app_online:
        return JSONResponse({"error": "main app offline"}, status_code=503)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{MAIN_APP_URL}/control/restart/detector")
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/restart/health")
async def restart_health() -> JSONResponse:
    if not _state.app_online:
        return JSONResponse({"error": "main app offline"}, status_code=503)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{MAIN_APP_URL}/control/restart/health")
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/restart/service")
async def restart_service() -> JSONResponse:
    result = subprocess.run(
        ["sudo", "systemctl", "restart", "pi-people-detector"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return JSONResponse({"error": result.stderr}, status_code=500)
    return JSONResponse({"status": "restarting"})
```

- [ ] **Step 4: Run monitor tests**

```bash
python3 -m pytest tests/test_monitor.py -v
```

Expected: all 7 PASS

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat: add monitor sidecar process with status, restart, and log proxy endpoints"
```

---

### Task 7: Create `monitor_static/index.html`

**Files:**
- Create: `monitor_static/index.html`

No automated tests for HTML/JS. Manual verification steps provided instead.

- [ ] **Step 1: Create the directory**

```bash
mkdir -p monitor_static
```

- [ ] **Step 2: Create `monitor_static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pi Monitor</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: monospace; background: #0d0d0d; color: #e0e0e0; padding: 2rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        .title { font-size: 1.2rem; color: #888; letter-spacing: 0.2em; }
        .tabs { display: flex; gap: 0.5rem; }
        .tab-btn { background: #1e1e1e; border: 1px solid #333; color: #666; padding: 0.4rem 1rem; cursor: pointer; font-family: monospace; font-size: 0.85rem; }
        .tab-btn.active { border-color: #ccc; color: #ccc; }
        .tab-btn:hover { background: #2a2a2a; }
        .tab-pane { display: none; }
        .tab-pane.active { display: block; }
        .service-banner { display: flex; justify-content: space-between; align-items: center; background: #1a1a1a; border: 1px solid #333; padding: 0.75rem 1rem; margin-bottom: 1.5rem; }
        .service-name { font-size: 0.9rem; color: #ccc; }
        .service-status { display: flex; align-items: center; gap: 0.75rem; }
        .section-title { font-size: 0.8rem; color: #666; letter-spacing: 0.1em; margin-bottom: 0.75rem; }
        .component-grid { margin-bottom: 1.5rem; }
        .component-row { display: grid; grid-template-columns: 8px 120px 1fr auto; align-items: start; gap: 0.75rem; padding: 0.6rem 0; border-bottom: 1px solid #1a1a1a; font-size: 0.85rem; }
        .component-info { display: flex; flex-direction: column; gap: 0.2rem; }
        .component-error { font-size: 0.75rem; color: #f44336; cursor: pointer; word-break: break-all; }
        .component-error-time { font-size: 0.7rem; color: #555; }
        .log-controls { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; align-items: center; }
        .log-select { background: #1e1e1e; border: 1px solid #333; color: #ccc; padding: 0.3rem 0.5rem; font-family: monospace; font-size: 0.85rem; }
        .log-entries { background: #111; border: 1px solid #222; padding: 0.75rem; height: 220px; overflow-y: auto; font-size: 0.75rem; }
        .log-entry { display: flex; gap: 1rem; margin-bottom: 0.25rem; line-height: 1.4; }
        .log-ts { color: #555; white-space: nowrap; }
        .log-ERROR { color: #f44336; }
        .log-INFO { color: #4caf50; }
        .log-WARN { color: #ff9800; }
        .log-msg { color: #aaa; word-break: break-all; }
        .count-panel { text-align: center; margin-bottom: 2rem; }
        .count-label { font-size: 0.9rem; color: #666; letter-spacing: 0.15em; margin-bottom: 0.5rem; }
        .count-value { font-size: 6rem; font-weight: bold; color: #fff; line-height: 1; }
        .health-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; }
        .health-card { background: #1a1a1a; border: 1px solid #222; padding: 0.75rem; }
        .health-card-label { font-size: 0.75rem; color: #666; margin-bottom: 0.3rem; }
        .health-card-value { font-size: 1.1rem; color: #ccc; }
        .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; margin-top: 4px; }
        .dot.ok { background: #4caf50; }
        .dot.err { background: #f44336; }
        .dot.warn { background: #ff9800; }
        .btn { background: #1e1e1e; border: 1px solid #333; color: #ccc; padding: 0.3rem 0.75rem; cursor: pointer; font-family: monospace; font-size: 0.8rem; white-space: nowrap; }
        .btn:hover { background: #2a2a2a; }
        .btn-danger { border-color: #f44336; color: #f44336; }
        .btn-danger:hover { background: #1a0a0a; }
        .offline-banner { background: #1a0a0a; border: 1px solid #f44336; padding: 0.5rem 1rem; margin-bottom: 1rem; font-size: 0.85rem; color: #f44336; display: none; }
        .ws-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; font-size: 0.8rem; color: #666; }
        .preview-btn { background: #1e1e1e; border: 1px solid #333; color: #ccc; padding: 0.5rem 1rem; cursor: pointer; font-family: monospace; font-size: 0.85rem; display: block; margin-bottom: 0.75rem; }
        #camera-img { width: 100%; max-width: 640px; display: block; border: 1px solid #333; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">PI MONITOR</div>
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('ops')">OPS</button>
            <button class="tab-btn" onclick="switchTab('live')">LIVE</button>
        </div>
    </div>

    <div id="tab-ops" class="tab-pane active">
        <div class="offline-banner" id="offline-banner"></div>

        <div class="service-banner">
            <span class="service-name">pi-people-detector</span>
            <div class="service-status">
                <span class="dot err" id="service-dot"></span>
                <span id="service-status-text" style="font-size:0.85rem;color:#888">—</span>
                <button class="btn btn-danger" onclick="restartService()">Restart Service</button>
            </div>
        </div>

        <div class="section-title">COMPONENTS</div>
        <div class="component-grid">
            <div class="component-row">
                <span class="dot err" id="dot-camera"></span>
                <span style="color:#888">Camera</span>
                <div class="component-info">
                    <span class="component-error" id="err-camera" style="display:none" onclick="toggleErr('camera')"></span>
                    <span class="component-error-time" id="err-camera-at"></span>
                </div>
                <button class="btn" onclick="restartComponent('detector')">Restart</button>
            </div>
            <div class="component-row">
                <span class="dot err" id="dot-yolo"></span>
                <span style="color:#888">YOLO</span>
                <div class="component-info">
                    <span class="component-error" id="err-yolo" style="display:none" onclick="toggleErr('yolo')"></span>
                    <span class="component-error-time" id="err-yolo-at"></span>
                </div>
                <button class="btn" onclick="restartComponent('detector')">Restart</button>
            </div>
            <div class="component-row">
                <span class="dot err" id="dot-health"></span>
                <span style="color:#888">Health</span>
                <div class="component-info">
                    <span class="component-error" id="err-health" style="display:none" onclick="toggleErr('health')"></span>
                    <span class="component-error-time" id="err-health-at"></span>
                </div>
                <button class="btn" onclick="restartComponent('health')">Restart</button>
            </div>
        </div>

        <div class="section-title">LOGS</div>
        <div class="log-controls">
            <select class="log-select" id="log-component">
                <option value="detector">Detector</option>
                <option value="health">Health</option>
                <option value="stream">Stream</option>
            </select>
            <button class="btn" onclick="loadLogs()">Refresh</button>
        </div>
        <div class="log-entries" id="log-entries">
            <span style="color:#444">Select a component and click Refresh</span>
        </div>
    </div>

    <div id="tab-live" class="tab-pane">
        <div class="count-panel">
            <div class="count-label">PEOPLE IN FRAME</div>
            <div class="count-value" id="live-count">—</div>
        </div>
        <div class="health-grid">
            <div class="health-card">
                <div class="health-card-label">CPU</div>
                <div class="health-card-value" id="live-cpu">—</div>
            </div>
            <div class="health-card">
                <div class="health-card-label">RAM</div>
                <div class="health-card-value" id="live-ram">—</div>
            </div>
            <div class="health-card">
                <div class="health-card-label">TEMP</div>
                <div class="health-card-value" id="live-temp">—</div>
            </div>
            <div class="health-card">
                <div class="health-card-label">DISK</div>
                <div class="health-card-value" id="live-disk">—</div>
            </div>
        </div>
        <div class="ws-row">
            <span class="dot err" id="live-ws-dot"></span>
            <span>WebSocket</span>
        </div>
        <button class="preview-btn" id="preview-btn" onclick="togglePreview()">Open Camera Preview</button>
        <img id="camera-img" alt="Camera preview" style="display:none" />
    </div>

    <script>
        var currentTab = 'ops';
        var opsTimer = null;
        var liveTimer = null;
        var ws = null;
        var wsDelay = 1000;
        var MAIN = location.protocol + '//' + location.hostname + ':8000';

        // ── Tab switching ──────────────────────────────────────────────
        function switchTab(tab) {
            document.getElementById('tab-' + currentTab).classList.remove('active');
            document.querySelectorAll('.tab-btn')[tab === 'ops' ? 0 : 1].classList.add('active');
            document.querySelectorAll('.tab-btn')[tab === 'ops' ? 1 : 0].classList.remove('active');
            document.getElementById('tab-' + tab).classList.add('active');
            if (currentTab === 'live') stopLive();
            currentTab = tab;
            if (tab === 'live') startLive(); else startOps();
        }

        // ── OPS tab ────────────────────────────────────────────────────
        function startOps() {
            pollOps();
            opsTimer = setInterval(pollOps, 3000);
        }

        function stopOps() {
            clearInterval(opsTimer);
            opsTimer = null;
        }

        function pollOps() {
            fetch('/api/status')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var banner = document.getElementById('offline-banner');
                    if (!d.app_online) {
                        var since = d.app_offline_since ? ' since ' + relTime(d.app_offline_since) : '';
                        banner.textContent = '● Main app offline' + since;
                        banner.style.display = 'block';
                    } else {
                        banner.style.display = 'none';
                    }
                    var dot = document.getElementById('service-dot');
                    dot.className = 'dot ' + (d.app_online ? 'ok' : 'err');
                    document.getElementById('service-status-text').textContent = d.app_online ? 'Active' : 'Offline';
                    setComp('camera', d.camera_ok, d.camera_error, d.camera_error_at);
                    setComp('yolo',   d.model_ok,  d.model_error,  d.model_error_at);
                    var healthOk = !d.health_error && d.ram_total > 0;
                    setComp('health', healthOk, d.health_error, d.health_error_at);
                })
                .catch(function() {
                    var banner = document.getElementById('offline-banner');
                    banner.textContent = '● Monitor unreachable';
                    banner.style.display = 'block';
                });
        }

        function setComp(name, ok, err, errAt) {
            var dot = document.getElementById('dot-' + name);
            var errEl = document.getElementById('err-' + name);
            var atEl = document.getElementById('err-' + name + '-at');
            dot.className = 'dot ' + (ok ? 'ok' : (err ? 'err' : 'warn'));
            if (err) {
                errEl._full = err;
                errEl._short = err.length > 80 ? err.slice(0, 80) + '…' : err;
                errEl._expanded = false;
                errEl.textContent = errEl._short;
                errEl.style.display = 'block';
                atEl.textContent = errAt ? relTime(errAt) : '';
            } else {
                errEl.style.display = 'none';
                atEl.textContent = '';
            }
        }

        function toggleErr(name) {
            var el = document.getElementById('err-' + name);
            el._expanded = !el._expanded;
            el.textContent = el._expanded ? el._full : el._short;
        }

        function loadLogs() {
            var comp = document.getElementById('log-component').value;
            var box = document.getElementById('log-entries');
            box.innerHTML = '<span style="color:#444">Loading…</span>';
            fetch('/api/logs/' + comp)
                .then(function(r) { return r.json(); })
                .then(function(entries) {
                    if (!entries.length) {
                        box.innerHTML = '<span style="color:#444">No entries</span>';
                        return;
                    }
                    box.innerHTML = entries.map(function(e) {
                        return '<div class="log-entry">' +
                            '<span class="log-ts">' + fmtTs(e.ts) + '</span>' +
                            '<span class="log-' + e.level + '">' + e.level + '</span>' +
                            '<span class="log-msg">' + esc(e.msg) + '</span>' +
                            '</div>';
                    }).join('');
                    box.scrollTop = box.scrollHeight;
                })
                .catch(function() {
                    box.innerHTML = '<span style="color:#f44336">Failed to load</span>';
                });
        }

        function restartComponent(comp) {
            fetch('/api/restart/' + comp, { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function() { setTimeout(pollOps, 1500); })
                .catch(function() { alert('Restart request failed'); });
        }

        function restartService() {
            if (!confirm('Restart pi-people-detector service?\nThe app will be offline for a few seconds.')) return;
            fetch('/api/restart/service', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function() { setTimeout(pollOps, 4000); })
                .catch(function() { alert('Restart failed'); });
        }

        // ── LIVE tab ───────────────────────────────────────────────────
        function startLive() {
            connectWS();
            pollLive();
            liveTimer = setInterval(pollLive, 3000);
        }

        function stopLive() {
            clearInterval(liveTimer);
            liveTimer = null;
            if (ws) { ws.close(); ws = null; }
            var img = document.getElementById('camera-img');
            if (img.style.display !== 'none') togglePreview();
        }

        function connectWS() {
            if (currentTab !== 'live') return;
            var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(proto + '//' + location.hostname + ':8000/ws');
            ws.onopen = function() {
                document.getElementById('live-ws-dot').className = 'dot ok';
                wsDelay = 1000;
            };
            ws.onmessage = function(e) {
                document.getElementById('live-count').textContent = JSON.parse(e.data).count;
            };
            ws.onclose = ws.onerror = function() {
                document.getElementById('live-ws-dot').className = 'dot err';
                if (currentTab === 'live') {
                    setTimeout(connectWS, wsDelay);
                    wsDelay = Math.min(wsDelay * 2, 30000);
                }
            };
        }

        function pollLive() {
            fetch(MAIN + '/health')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    document.getElementById('live-cpu').textContent = d.cpu_percent.toFixed(1) + '%';
                    document.getElementById('live-ram').textContent = d.ram_total > 0
                        ? ((d.ram_used / d.ram_total) * 100).toFixed(1) + '%' : '—';
                    document.getElementById('live-temp').textContent = d.cpu_temp != null
                        ? d.cpu_temp.toFixed(1) + '°C' : '—';
                    document.getElementById('live-disk').textContent = d.disk_total > 0
                        ? ((d.disk_used / d.disk_total) * 100).toFixed(1) + '%' : '—';
                })
                .catch(function() {});
        }

        function togglePreview() {
            var img = document.getElementById('camera-img');
            var btn = document.getElementById('preview-btn');
            if (img.style.display === 'none') {
                img.src = MAIN + '/stream';
                img.style.display = 'block';
                btn.textContent = 'Close Camera Preview';
            } else {
                img.src = '';
                img.style.display = 'none';
                btn.textContent = 'Open Camera Preview';
            }
        }

        // ── Helpers ────────────────────────────────────────────────────
        function relTime(ts) {
            var diff = Math.floor(Date.now() / 1000 - ts);
            if (diff < 60) return diff + 's ago';
            if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
            return Math.floor(diff / 3600) + 'h ago';
        }

        function fmtTs(ts) {
            return new Date(ts * 1000).toLocaleTimeString();
        }

        function esc(s) {
            return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        // ── Boot ───────────────────────────────────────────────────────
        startOps();
    </script>
</body>
</html>
```

- [ ] **Step 3: Verify `monitor.py` serves the file**

```bash
python3 -m pytest tests/test_monitor.py -v
```

Expected: all 7 still PASS (HTML file now present, no regressions)

- [ ] **Step 4: Commit**

```bash
git add monitor_static/index.html
git commit -m "feat: add two-tab management dashboard UI"
```

---

### Task 8: Update `install.sh` — add pi-monitor service

**Files:**
- Modify: `install.sh`

No automated tests for install.sh changes. Manual verification on Pi required.

- [ ] **Step 1: Update `install.sh`**

Replace the `echo "[3/4]..."` block and `echo "[4/4]..."` block with a 5-step version:

```bash
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
```

- [ ] **Step 2: Verify shell syntax**

```bash
bash -n install.sh
```

Expected: no output, exit code 0

- [ ] **Step 3: Run full test suite one final time**

```bash
python3 -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add install.sh
git commit -m "feat: add pi-monitor systemd service to install.sh"
```
