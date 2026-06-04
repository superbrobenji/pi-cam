# Unique People Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add YOLOv8 ByteTrack-based people tracking to emit four WebSocket fields — `rawCount`, `enteredFrame`, `firstSeen`, `uniqueTotal` — and display them on the LIVE dashboard tab with a reset button.

**Architecture:** `SharedState` gains four new fields (`entered_frame`, `first_seen`, `unique_total`, `reset_tracking`). The detector switches from `model()` to `model.track()`, computing per-tick tracking stats and honouring a `reset_tracking` flag. The WebSocket payload is updated to use new field names. A reset endpoint is added to both `main.py` and `monitor.py`. The dashboard replaces the single count display with a 2×2 people grid and a reset button.

**Tech Stack:** Python 3.9, ultralytics YOLOv8 ByteTrack, FastAPI, vanilla JS

---

## File Map

| File | Action |
|---|---|
| `shared_state.py` | Add `entered_frame`, `first_seen`, `unique_total`, `reset_tracking` |
| `detector.py` | Switch to `model.track()`, compute tracking fields, check reset flag; mock loop sets tracking fields to 0 |
| `main.py` | WebSocket sends 4 fields; add `POST /control/reset-tracking` |
| `monitor.py` | Add `POST /api/reset-tracking` proxy |
| `monitor_static/index.html` | Replace count panel with 4-card people grid, add reset button, update WS handler |
| `tests/test_shared_state.py` | Add assertions for 4 new fields |
| `tests/test_integration.py` | Update WS test to expect `rawCount`; add reset endpoint test |
| `tests/test_monitor.py` | Add reset proxy tests |
| `tests/test_detector.py` | Add test that mock loop sets tracking fields to 0 |

---

### Task 1: Extend SharedState with tracking fields

**Files:**
- Modify: `shared_state.py`
- Modify: `tests/test_shared_state.py`

- [ ] **Step 1: Write failing test — update `test_initial_values`**

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
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_shared_state.py::test_initial_values -v
```

Expected: FAIL — `KeyError: 'entered_frame'`

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
    "entered_frame", "first_seen", "unique_total", "reset_tracking",
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
git commit -m "feat: add tracking fields to SharedState"
```

---

### Task 2: Update `detector.py` — tracking + reset

**Files:**
- Modify: `detector.py`
- Modify: `tests/test_detector.py`

- [ ] **Step 1: Write failing test — mock sets tracking fields to 0**

Add to `tests/test_detector.py`:

```python
def test_mock_sets_tracking_fields_to_zero():
    state = SharedState()
    _start_detector(state)
    snap = state.snapshot()
    assert snap["entered_frame"] == 0
    assert snap["first_seen"] == 0
    assert snap["unique_total"] == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_detector.py::test_mock_sets_tracking_fields_to_zero -v
```

Expected: FAIL — `AssertionError` (fields not set by mock loop yet)

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
        state.update(
            camera_ok=True, count=0,
            entered_frame=0, first_seen=0, unique_total=0,
        )
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
    prev_ids: set = set()
    all_seen_ids: set = set()

    while not stop_event.is_set():
        t0 = time.monotonic()

        if state.reset_tracking:
            prev_ids.clear()
            all_seen_ids.clear()
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

            results = model.track(frame, persist=True, verbose=False)[0]

            person_indices = [
                i for i, box in enumerate(results.boxes)
                if int(box.cls[0]) == _PERSON_CLASS_ID
                and float(box.conf[0]) >= _CONFIDENCE_THRESHOLD
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
            )

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

Expected: all 8 PASS (7 existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add detector.py tests/test_detector.py
git commit -m "feat: switch to model.track() with enteredFrame/firstSeen/uniqueTotal tracking"
```

---

### Task 3: Update `main.py` — WebSocket payload + reset endpoint

**Files:**
- Modify: `main.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_integration.py`, replace `test_websocket_emits_count`:

```python
def test_websocket_emits_count(client):
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "rawCount" in data
        assert "enteredFrame" in data
        assert "firstSeen" in data
        assert "uniqueTotal" in data
        assert isinstance(data["rawCount"], int)
        assert isinstance(data["enteredFrame"], int)
        assert isinstance(data["firstSeen"], int)
        assert isinstance(data["uniqueTotal"], int)
```

Also append a new test:

```python
def test_reset_tracking_returns_ok(client):
    resp = client.post("/control/reset-tracking")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m pytest tests/test_integration.py::test_websocket_emits_count tests/test_integration.py::test_reset_tracking_returns_ok -v
```

Expected: both FAIL

- [ ] **Step 3: Update `main.py`**

Change the WebSocket send line (currently `await websocket.send_json({"count": state.count})`):

```python
await websocket.send_json({
    "rawCount": state.count,
    "enteredFrame": state.entered_frame,
    "firstSeen": state.first_seen,
    "uniqueTotal": state.unique_total,
})
```

Add the reset endpoint after `restart_health`:

```python
@app.post("/control/reset-tracking")
async def reset_tracking() -> JSONResponse:
    state.update(reset_tracking=True)
    log_buffer.append("detector", "INFO", "Tracking reset requested")
    return JSONResponse({"status": "ok"})
```

- [ ] **Step 4: Run integration tests**

```bash
python3 -m pytest tests/test_integration.py -v
```

Expected: all 13 PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "feat: websocket sends 4 tracking fields, add reset-tracking endpoint"
```

---

### Task 4: Update `monitor.py` — reset proxy

**Files:**
- Modify: `monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_monitor.py`:

```python
def test_reset_tracking_returns_503_when_offline(client):
    _monitor_module._state.app_online = False
    resp = client.post("/api/reset-tracking")
    assert resp.status_code == 503
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_monitor.py::test_reset_tracking_returns_503_when_offline -v
```

Expected: FAIL — endpoint doesn't exist yet

- [ ] **Step 3: Add endpoint to `monitor.py`**

Append after `restart_service`:

```python
@app.post("/api/reset-tracking")
async def reset_tracking() -> JSONResponse:
    if not _state.app_online:
        return JSONResponse({"error": "main app offline"}, status_code=503)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{MAIN_APP_URL}/control/reset-tracking")
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
```

- [ ] **Step 4: Run all monitor tests**

```bash
python3 -m pytest tests/test_monitor.py -v
```

Expected: all 9 PASS

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -v
```

Expected: all 44 PASS (41 prior + 1 detector + 1 integration + 1 monitor)

- [ ] **Step 6: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat: add reset-tracking proxy to monitor"
```

---

### Task 5: Update dashboard — 4-card people grid + reset button

**Files:**
- Modify: `monitor_static/index.html`

No automated tests. Manual verification steps at end.

- [ ] **Step 1: Replace count panel with 4-card people grid**

In `monitor_static/index.html`, replace:

```html
    <div id="tab-live" class="tab-pane active">
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
```

With:

```html
    <div id="tab-live" class="tab-pane active">
        <div class="section-title" style="margin-bottom:0.75rem">PEOPLE</div>
        <div class="health-grid" style="margin-bottom:0.75rem">
            <div class="health-card">
                <div class="health-card-label">IN FRAME</div>
                <div class="health-card-value" id="live-raw-count">—</div>
            </div>
            <div class="health-card">
                <div class="health-card-label">ENTERED</div>
                <div class="health-card-value" id="live-entered-frame">—</div>
            </div>
            <div class="health-card">
                <div class="health-card-label">FIRST SEEN</div>
                <div class="health-card-value" id="live-first-seen">—</div>
            </div>
            <div class="health-card">
                <div class="health-card-label">TOTAL UNIQUE</div>
                <div class="health-card-value" id="live-unique-total">—</div>
            </div>
        </div>
        <button class="btn btn-danger" style="margin-bottom:1.5rem" onclick="resetTracking()">Reset Unique Count</button>
        <div class="section-title" style="margin-bottom:0.75rem">SYSTEM</div>
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
```

- [ ] **Step 2: Update WebSocket message handler**

Find and replace:

```js
            ws.onmessage = function(e) {
                document.getElementById('live-count').textContent = JSON.parse(e.data).count;
            };
```

With:

```js
            ws.onmessage = function(e) {
                var d = JSON.parse(e.data);
                document.getElementById('live-raw-count').textContent = d.rawCount;
                document.getElementById('live-entered-frame').textContent = d.enteredFrame;
                document.getElementById('live-first-seen').textContent = d.firstSeen;
                document.getElementById('live-unique-total').textContent = d.uniqueTotal;
            };
```

- [ ] **Step 3: Add `resetTracking()` function**

Append inside the `<script>` block, before the closing IIFE:

```js
        function resetTracking() {
            if (!confirm('Reset unique total? This cannot be undone.')) return;
            fetch('/api/reset-tracking', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .catch(function() { alert('Reset failed'); });
        }
```

- [ ] **Step 4: Remove unused CSS**

Remove these unused CSS rules (no longer needed after removing `.count-panel`):

```css
        .count-panel { text-align: center; margin-bottom: 2rem; }
        .count-label { font-size: 0.9rem; color: #666; letter-spacing: 0.15em; margin-bottom: 0.5rem; }
        .count-value { font-size: 6rem; font-weight: bold; color: #fff; line-height: 1; }
```

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
python3 -m pytest -v
```

Expected: all 44 PASS

- [ ] **Step 6: Manual verification**

Start monitor with mock camera:
```bash
MOCK_CAMERA=1 uvicorn main:app --port 8000 &
uvicorn monitor:app --port 8001
```

Open `http://localhost:8001`. On the LIVE tab verify:
- Four people cards visible (IN FRAME, ENTERED, FIRST SEEN, TOTAL UNIQUE) all showing `0`
- SYSTEM section shows CPU/RAM/TEMP/DISK
- "Reset Unique Count" button shows confirm dialog when clicked
- Confirm resets values; cancel does nothing

- [ ] **Step 7: Commit**

```bash
git add monitor_static/index.html
git commit -m "feat: replace count panel with 4-card people grid and reset button"
```
