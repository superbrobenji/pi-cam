# Detection Accuracy & Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade detection to yolov8s, make model/confidence/IoU configurable at runtime via a dashboard settings panel, and switch WebSocket to event-driven delivery with a 1-second minimum floor.

**Architecture:** SharedState gains four new fields for settings + inference tick. Detector reads thresholds from state each tick and fires an `on_inference` callback. Main app stores an asyncio.Event + event loop reference; the WS loop awaits the event instead of sleeping. A `/control/settings` endpoint updates state and optionally restarts the detector. Monitor proxies settings reads and writes. Dashboard gets a DETECTION settings panel and hollow error dots.

**Tech Stack:** Python 3.9, FastAPI, asyncio, ultralytics YOLOv8, vanilla JS

---

## File Map

| File | Action |
|---|---|
| `shared_state.py` | Add `model_name`, `confidence_threshold`, `iou_threshold`, `inference_tick` |
| `detector.py` | `on_inference` callback, read thresholds from state, remove `_CONFIDENCE_THRESHOLD` constant, use `state.model_name` |
| `main.py` | `_inference_event` + `_event_loop`, event-driven WS, `POST /control/settings`, pass callback to detector |
| `monitor.py` | `GET /api/settings`, `POST /api/settings` — add `Request` import |
| `monitor_static/index.html` | Hollow `.dot.err` style, DETECTION section, `loadSettings()`, `applySettings()` |
| `tests/test_shared_state.py` | Assert 4 new fields in `test_initial_values` |
| `tests/test_detector.py` | Test `on_inference` fires in mock; test `inference_tick` increments |
| `tests/test_integration.py` | Test settings endpoint: valid, invalid model, invalid threshold |
| `tests/test_monitor.py` | Test GET settings keys; POST settings 503 when offline |

---

### Task 1: Extend SharedState with settings + tick fields

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
    assert snap["entered_frame"] == 0
    assert snap["first_seen"] == 0
    assert snap["unique_total"] == 0
    assert snap["reset_tracking"] is False
    assert snap["model_name"] == "yolov8s.pt"
    assert snap["confidence_threshold"] == 0.65
    assert snap["iou_threshold"] == 0.60
    assert snap["inference_tick"] == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_shared_state.py::test_initial_values -v
```

Expected: FAIL — `KeyError: 'model_name'`

- [ ] **Step 3: Replace `shared_state.py`**

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
    "entered_frame", "first_seen", "unique_total", "reset_tracking",
    "model_name", "confidence_threshold", "iou_threshold", "inference_tick",
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
        self.entered_frame = 0
        self.first_seen = 0
        self.unique_total = 0
        self.reset_tracking = False
        self.model_name = "yolov8s.pt"
        self.confidence_threshold = 0.65
        self.iou_threshold = 0.60
        self.inference_tick = 0

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
                "entered_frame": self.entered_frame,
                "first_seen": self.first_seen,
                "unique_total": self.unique_total,
                "reset_tracking": self.reset_tracking,
                "model_name": self.model_name,
                "confidence_threshold": self.confidence_threshold,
                "iou_threshold": self.iou_threshold,
                "inference_tick": self.inference_tick,
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
git commit -m "feat: add model/threshold/tick settings fields to SharedState"
```

---

### Task 2: Update `detector.py` — on_inference callback, thresholds from state, inference_tick

**Files:**
- Modify: `detector.py`
- Modify: `tests/test_detector.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_detector.py`:

```python
def test_mock_increments_inference_tick():
    state = SharedState()
    _start_detector(state)
    assert state.snapshot()["inference_tick"] > 0


def test_on_inference_callback_fires_in_mock():
    state = SharedState()
    calls = []
    stop = threading.Event()
    t = threading.Thread(
        target=run_detector,
        args=(state, stop, lambda: calls.append(1)),
        daemon=True,
    )
    t.start()
    time.sleep(0.4)
    stop.set()
    t.join(timeout=3.0)
    assert len(calls) > 0
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m pytest tests/test_detector.py::test_mock_increments_inference_tick tests/test_detector.py::test_on_inference_callback_fires_in_mock -v
```

Expected: both FAIL — `inference_tick` not updated, `on_inference` not accepted

- [ ] **Step 3: Replace `detector.py`**

```python
import os
import time
import threading
import cv2
import numpy as np
from typing import Callable, Optional
import log_buffer
from shared_state import SharedState

_MOCK_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
_PERSON_CLASS_ID = 0


def _encode_jpeg(frame: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def run_detector(
    state: SharedState,
    stop_event: Optional[threading.Event] = None,
    on_inference: Optional[Callable] = None,
) -> None:
    if stop_event is None:
        stop_event = threading.Event()
    if os.environ.get("MOCK_CAMERA") == "1":
        state.update(model_ok=True)
        _run_mock_loop(state, stop_event, on_inference)
    else:
        _run_live_loop(state, stop_event, on_inference)


def _run_mock_loop(
    state: SharedState,
    stop_event: threading.Event,
    on_inference: Optional[Callable] = None,
) -> None:
    while not stop_event.is_set():
        t0 = time.monotonic()
        if state.stream_active:
            state.update(frame=_encode_jpeg(_MOCK_FRAME))
        state.update(
            camera_ok=True, count=0,
            entered_frame=0, first_seen=0, unique_total=0,
            inference_tick=state.inference_tick + 1,
        )
        if on_inference:
            on_inference()
        stop_event.wait(max(0.0, 1.0 - (time.monotonic() - t0)))


def _run_live_loop(
    state: SharedState,
    stop_event: threading.Event,
    on_inference: Optional[Callable] = None,
) -> None:
    from ultralytics import YOLO

    try:
        model = YOLO(state.model_name)
        state.update(model_ok=True, model_error=None, model_error_at=None)
    except Exception as e:
        msg = str(e)
        log_buffer.append("detector", "ERROR", f"Model load failed: {msg}")
        state.update(model_ok=False, model_error=msg, model_error_at=time.time())
        return

    cap = None
    retry_delay = 2.0
    prev_ids: set = set()
    all_seen_ids: set = set()

    while not stop_event.is_set():
        t0 = time.monotonic()

        if state.reset_tracking:
            prev_ids = set()
            all_seen_ids = set()
            state.update(
                reset_tracking=False,
                unique_total=0,
                first_seen=0,
                entered_frame=0,
            )

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

            results = model.track(
                frame, persist=True, verbose=False,
                iou=state.iou_threshold,
            )[0]

            person_indices = [
                i for i, box in enumerate(results.boxes)
                if int(box.cls[0]) == _PERSON_CLASS_ID
                and float(box.conf[0]) >= state.confidence_threshold
            ]

            if results.boxes.id is not None:
                track_ids = results.boxes.id.int().cpu().flatten().tolist()
                ids = set(track_ids[i] for i in person_indices)
            else:
                ids = set()

            entered_frame = len(ids - prev_ids)
            new_ids = ids - all_seen_ids
            all_seen_ids.update(ids)
            prev_ids = ids

            del results
            state.update(
                count=len(person_indices),
                entered_frame=entered_frame,
                first_seen=len(new_ids),
                unique_total=len(all_seen_ids),
                inference_tick=state.inference_tick + 1,
            )
            if on_inference:
                on_inference()

        except Exception as e:
            msg = str(e)
            log_buffer.append("detector", "ERROR", msg)
            state.update(
                camera_ok=False, count=0,
                entered_frame=0, first_seen=0,
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

Expected: all 10 PASS (8 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add detector.py tests/test_detector.py
git commit -m "feat: on_inference callback, read thresholds from state, increment inference_tick"
```

---

### Task 3: Update `main.py` — inference event, event-driven WS, settings endpoint

**Files:**
- Modify: `main.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_integration.py`:

```python
def test_settings_returns_ok(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 0.70,
        "iou_threshold": 0.55,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "restarted" in resp.json()


def test_settings_rejects_invalid_model(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8x.pt",
        "confidence_threshold": 0.65,
        "iou_threshold": 0.60,
    })
    assert resp.status_code == 422


def test_settings_rejects_invalid_threshold(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 1.5,
        "iou_threshold": 0.60,
    })
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m pytest tests/test_integration.py::test_settings_returns_ok tests/test_integration.py::test_settings_rejects_invalid_model tests/test_integration.py::test_settings_rejects_invalid_threshold -v
```

Expected: all 3 FAIL

- [ ] **Step 3: Replace `main.py`**

```python
import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response, StreamingResponse
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

_inference_event = asyncio.Event()
_event_loop: Optional[asyncio.AbstractEventLoop] = None

_VALID_MODELS = {"yolov8n.pt", "yolov8s.pt", "yolov8m.pt"}


def _on_inference() -> None:
    if _event_loop is not None:
        _event_loop.call_soon_threadsafe(_inference_event.set)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop
    _event_loop = asyncio.get_running_loop()
    threading.Thread(target=run_detector, args=(state, _detector_stop, _on_inference), daemon=True).start()
    threading.Thread(target=run_health_poller, args=(state, 2.0, _health_stop), daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


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
        last_sent = 0.0
        while True:
            try:
                await asyncio.wait_for(_inference_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            _inference_event.clear()

            now = asyncio.get_running_loop().time()
            remaining = 1.0 - (now - last_sent)
            if remaining > 0:
                await asyncio.sleep(remaining)

            await websocket.send_json({
                "rawCount": state.count,
                "enteredFrame": state.entered_frame,
                "firstSeen": state.first_seen,
                "uniqueTotal": state.unique_total,
            })
            last_sent = asyncio.get_running_loop().time()
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
        state.update(stream_error=msg, stream_error_at=asyncio.get_running_loop().time())
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


@app.post("/control/restart/detector")
async def restart_detector() -> JSONResponse:
    global _detector_stop
    _detector_stop.set()
    _detector_stop = threading.Event()
    log_buffer.append("detector", "INFO", "Restart requested via /control/restart/detector")
    threading.Thread(target=run_detector, args=(state, _detector_stop, _on_inference), daemon=True).start()
    return JSONResponse({"status": "restarting"})


@app.post("/control/restart/health")
async def restart_health() -> JSONResponse:
    global _health_stop
    _health_stop.set()
    _health_stop = threading.Event()
    log_buffer.append("health", "INFO", "Restart requested via /control/restart/health")
    threading.Thread(target=run_health_poller, args=(state, 2.0, _health_stop), daemon=True).start()
    return JSONResponse({"status": "restarting"})


@app.post("/control/reset-tracking")
async def reset_tracking() -> JSONResponse:
    state.update(reset_tracking=True)
    log_buffer.append("detector", "INFO", "Tracking reset requested")
    return JSONResponse({"status": "ok"})


@app.post("/control/settings")
async def update_settings(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    model_name = body.get("model_name")
    confidence_threshold = body.get("confidence_threshold")
    iou_threshold = body.get("iou_threshold")

    if model_name not in _VALID_MODELS:
        return JSONResponse(
            {"error": f"model_name must be one of {sorted(_VALID_MODELS)}"},
            status_code=422,
        )
    if not isinstance(confidence_threshold, (int, float)) or not (0.1 <= confidence_threshold <= 0.99):
        return JSONResponse(
            {"error": "confidence_threshold must be a float between 0.1 and 0.99"},
            status_code=422,
        )
    if not isinstance(iou_threshold, (int, float)) or not (0.1 <= iou_threshold <= 0.99):
        return JSONResponse(
            {"error": "iou_threshold must be a float between 0.1 and 0.99"},
            status_code=422,
        )

    model_changed = model_name != state.model_name
    state.update(
        model_name=model_name,
        confidence_threshold=float(confidence_threshold),
        iou_threshold=float(iou_threshold),
    )

    restarted = False
    if model_changed:
        global _detector_stop
        _detector_stop.set()
        _detector_stop = threading.Event()
        log_buffer.append("detector", "INFO", f"Model changed to {model_name}, restarting")
        threading.Thread(
            target=run_detector,
            args=(state, _detector_stop, _on_inference),
            daemon=True,
        ).start()
        restarted = True

    return JSONResponse({"status": "ok", "restarted": restarted})


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

Expected: all 16 PASS (13 existing + 3 new)

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -v
```

Expected: all 49 PASS (44 prior + 2 detector + 3 integration)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "feat: event-driven websocket with 1s floor, add settings endpoint"
```

---

### Task 4: Update `monitor.py` — settings proxy

**Files:**
- Modify: `monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_monitor.py`:

```python
def test_get_settings_returns_expected_keys(client):
    data = client.get("/api/settings").json()
    assert "model_name" in data
    assert "confidence_threshold" in data
    assert "iou_threshold" in data


def test_post_settings_returns_503_when_offline(client):
    _monitor_module._state.app_online = False
    resp = client.post("/api/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 0.65,
        "iou_threshold": 0.60,
    })
    assert resp.status_code == 503
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m pytest tests/test_monitor.py::test_get_settings_returns_expected_keys tests/test_monitor.py::test_post_settings_returns_503_when_offline -v
```

Expected: both FAIL

- [ ] **Step 3: Add `Request` import and two endpoints to `monitor.py`**

Change the imports line from:
```python
from fastapi import FastAPI
```
to:
```python
from fastapi import FastAPI, Request
```

Append after the `reset_tracking` endpoint:

```python
@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    return JSONResponse({
        "model_name": _state.last_health.get("model_name", "yolov8s.pt"),
        "confidence_threshold": _state.last_health.get("confidence_threshold", 0.65),
        "iou_threshold": _state.last_health.get("iou_threshold", 0.60),
    })


@app.post("/api/settings")
async def post_settings(request: Request) -> JSONResponse:
    if not _state.app_online:
        return JSONResponse({"error": "main app offline"}, status_code=503)
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{MAIN_APP_URL}/control/settings", json=body)
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
```

- [ ] **Step 4: Run all monitor tests**

```bash
python3 -m pytest tests/test_monitor.py -v
```

Expected: all 11 PASS (9 existing + 2 new)

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -v
```

Expected: all 51 PASS

- [ ] **Step 6: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat: add settings GET/POST proxy to monitor"
```

---

### Task 5: Update `monitor_static/index.html` — hollow err dots + DETECTION settings panel

**Files:**
- Modify: `monitor_static/index.html`

No automated tests. Manual verification at end.

- [ ] **Step 1: Change `.dot.err` CSS to hollow ring**

Find:
```css
        .dot.err { background: #f44336; }
```

Replace with:
```css
        .dot.err { background: transparent; border: 2px solid #f44336; }
```

- [ ] **Step 2: Add DETECTION section to OPS tab**

Find the closing `</div>` of `id="tab-ops"` (the last `</div>` before `<div id="tab-live"`). Add before it:

```html
        <div class="section-title" style="margin-top:1.5rem;margin-bottom:0.75rem">DETECTION</div>
        <div style="display:flex;flex-direction:column;gap:0.75rem;max-width:320px">
            <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.85rem">
                <span style="color:#888">Model</span>
                <select id="setting-model" class="log-select">
                    <option value="yolov8n.pt">yolov8n (fast)</option>
                    <option value="yolov8s.pt">yolov8s (recommended)</option>
                    <option value="yolov8m.pt">yolov8m (⚠ runs hot)</option>
                </select>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.85rem">
                <span style="color:#888">Confidence</span>
                <input id="setting-confidence" type="number" min="0.1" max="0.99" step="0.05" value="0.65" class="log-select" style="width:80px" />
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.85rem">
                <span style="color:#888">IoU</span>
                <input id="setting-iou" type="number" min="0.1" max="0.99" step="0.05" value="0.60" class="log-select" style="width:80px" />
            </div>
            <div style="display:flex;align-items:center;gap:1rem">
                <button class="btn" onclick="applySettings()">Apply</button>
                <span id="settings-status" style="font-size:0.8rem;color:#4caf50"></span>
            </div>
        </div>
```

- [ ] **Step 3: Add `loadSettings()` and `applySettings()` JS functions**

Inside `<script>`, append before the closing IIFE `(function() {`:

```js
        function loadSettings() {
            fetch('/api/settings')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    document.getElementById('setting-model').value = d.model_name || 'yolov8s.pt';
                    document.getElementById('setting-confidence').value = d.confidence_threshold || 0.65;
                    document.getElementById('setting-iou').value = d.iou_threshold || 0.60;
                })
                .catch(function() {});
        }

        function applySettings() {
            var modelName = document.getElementById('setting-model').value;
            var confidence = parseFloat(document.getElementById('setting-confidence').value);
            var iou = parseFloat(document.getElementById('setting-iou').value);
            var statusEl = document.getElementById('settings-status');
            statusEl.textContent = 'Applying…';
            statusEl.style.color = '#888';
            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_name: modelName,
                    confidence_threshold: confidence,
                    iou_threshold: iou,
                }),
            })
            .then(function(r) {
                if (!r.ok) throw new Error('Server error: ' + r.status);
                return r.json();
            })
            .then(function(d) {
                statusEl.style.color = '#4caf50';
                statusEl.textContent = d.restarted ? 'Applied — detector restarting…' : 'Applied';
                setTimeout(function() { statusEl.textContent = ''; }, 3000);
            })
            .catch(function(e) {
                statusEl.style.color = '#f44336';
                statusEl.textContent = 'Failed: ' + e.message;
            });
        }
```

- [ ] **Step 4: Call `loadSettings()` inside `startOps()`**

Find:
```js
        function startOps() {
            stopOps();
            pollOps();
            opsTimer = setInterval(pollOps, 3000);
        }
```

Replace with:
```js
        function startOps() {
            stopOps();
            loadSettings();
            pollOps();
            opsTimer = setInterval(pollOps, 3000);
        }
```

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -v
```

Expected: all 51 PASS

- [ ] **Step 6: Manual verification**

Start with mock camera:
```bash
MOCK_CAMERA=1 uvicorn main:app --port 8000 &
uvicorn monitor:app --port 8001
```

Open `http://localhost:8001` → OPS tab:
- Error dots are hollow red rings, not filled
- DETECTION section visible with model dropdown, confidence, IoU inputs
- Current values loaded from `/api/settings`
- "Apply" button shows "Applied" confirmation
- Changing model to a different value shows "Applied — detector restarting…"

- [ ] **Step 7: Commit**

```bash
git add monitor_static/index.html
git commit -m "feat: hollow err dots, DETECTION settings panel with live apply"
```
