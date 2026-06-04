# Tracker Settings & Detection Panel Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix ByteTrack false positives caused by a 30-second default track buffer, add 5 configurable tracker parameters, and redesign the DETECTION dashboard panel with presets, model cards, and a confidence zone visualiser.

**Architecture:** SharedState gains 5 tracker fields with sensible defaults (track_memory_minutes=240 = 4 hours). Detector writes `bytetrack.yaml` from SharedState at startup and passes it to `model.track()`. Main app settings endpoint accepts and validates all 8 settings fields; restarts detector when model or any tracker param changes. Dashboard DETECTION section is replaced with two sub-sections (Detection + Tracking) each with presets, visual inputs, and clear descriptions.

**Tech Stack:** Python 3.9, ultralytics YOLOv8 ByteTrack, FastAPI, vanilla JS, CSS linear-gradient

---

## File Map

| File | Action |
|---|---|
| `shared_state.py` | Add 5 tracker fields |
| `bytetrack.yaml` | Create — written by detector at startup |
| `detector.py` | Write bytetrack.yaml, pass `tracker=` to model.track() |
| `main.py` | Extend `/control/settings` with 5 new fields + tracker restart logic |
| `monitor.py` | `GET /api/settings` returns all 8 fields with tracker defaults |
| `monitor_static/index.html` | Full DETECTION panel redesign |
| `tests/test_shared_state.py` | Assert 5 new initial values |
| `tests/test_integration.py` | Settings with tracker params; restart on tracker change |
| `tests/test_monitor.py` | GET settings returns tracker fields |

---

### Task 1: Extend SharedState with 5 tracker fields

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
    assert snap["track_memory_minutes"] == 240
    assert snap["track_high_thresh"] == 0.5
    assert snap["track_low_thresh"] == 0.1
    assert snap["new_track_thresh"] == 0.5
    assert snap["match_thresh"] == 0.8
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_shared_state.py::test_initial_values -v
```

Expected: FAIL — `KeyError: 'track_memory_minutes'`

- [ ] **Step 3: Update `shared_state.py`**

Add to `_FIELDS` frozenset (after `"inference_tick"`):

```python
    "track_memory_minutes", "track_high_thresh", "track_low_thresh",
    "new_track_thresh", "match_thresh",
```

Add to `__init__` (after `self.inference_tick = 0`):

```python
        self.track_memory_minutes = 240
        self.track_high_thresh = 0.5
        self.track_low_thresh = 0.1
        self.new_track_thresh = 0.5
        self.match_thresh = 0.8
```

Add to `snapshot()` return dict (after `"inference_tick": self.inference_tick`):

```python
                "track_memory_minutes": self.track_memory_minutes,
                "track_high_thresh": self.track_high_thresh,
                "track_low_thresh": self.track_low_thresh,
                "new_track_thresh": self.new_track_thresh,
                "match_thresh": self.match_thresh,
```

- [ ] **Step 4: Run all SharedState tests**

```bash
python3 -m pytest tests/test_shared_state.py -v
```

Expected: all 6 PASS

- [ ] **Step 5: Commit**

```bash
git add shared_state.py tests/test_shared_state.py
git commit -m "feat: add tracker fields to SharedState"
```

---

### Task 2: Update `detector.py` — write bytetrack.yaml + pass tracker param

**Files:**
- Modify: `detector.py`

No new tests needed (YAML writing is a live-loop side effect; existing tests cover mock mode which doesn't write the config).

- [ ] **Step 1: Add bytetrack config path + write function**

Add after the existing module-level constants at the top of `detector.py`:

```python
import os as _os
_BYTETRACK_CONFIG_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "bytetrack.yaml")


def _write_bytetrack_config(state: SharedState) -> None:
    content = (
        "tracker_type: bytetrack\n"
        f"track_high_thresh: {state.track_high_thresh}\n"
        f"track_low_thresh: {state.track_low_thresh}\n"
        f"new_track_thresh: {state.new_track_thresh}\n"
        f"track_buffer: {state.track_memory_minutes * 60}\n"
        f"match_thresh: {state.match_thresh}\n"
    )
    with open(_BYTETRACK_CONFIG_PATH, "w") as f:
        f.write(content)
```

- [ ] **Step 2: Call `_write_bytetrack_config` at start of `_run_live_loop` + pass tracker param**

In `_run_live_loop`, before the `try:` that loads the YOLO model:

```python
def _run_live_loop(
    state: SharedState,
    stop_event: threading.Event,
    on_inference: Optional[Callable] = None,
) -> None:
    from ultralytics import YOLO

    _write_bytetrack_config(state)

    try:
        model = YOLO(state.model_name)
        ...
```

In the `model.track()` call, add `tracker=_BYTETRACK_CONFIG_PATH`:

```python
            results = model.track(
                frame, persist=True, verbose=False,
                iou=state.iou_threshold,
                tracker=_BYTETRACK_CONFIG_PATH,
            )[0]
```

- [ ] **Step 3: Run full suite to check no regressions**

```bash
python3 -m pytest -q
```

Expected: all 51 PASS in under 10s

- [ ] **Step 4: Commit**

```bash
git add detector.py
git commit -m "feat: write bytetrack.yaml from state at detector startup, pass tracker param"
```

---

### Task 3: Update `main.py` + integration tests — extend settings endpoint

**Files:**
- Modify: `main.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Update existing settings tests + write new failing tests**

The existing `test_settings_returns_ok`, `test_settings_rejects_invalid_model`, and `test_settings_rejects_invalid_threshold` only send 3 fields — they will 422 once all 8 are required. Update them first, then append 3 new tests.

Replace the three existing settings tests:

```python
def test_settings_returns_ok(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 0.70,
        "iou_threshold": 0.55,
        "track_memory_minutes": 240,
        "track_high_thresh": 0.50,
        "track_low_thresh": 0.10,
        "new_track_thresh": 0.50,
        "match_thresh": 0.80,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "restarted" in resp.json()


def test_settings_rejects_invalid_model(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8x.pt",
        "confidence_threshold": 0.65,
        "iou_threshold": 0.60,
        "track_memory_minutes": 240,
        "track_high_thresh": 0.50,
        "track_low_thresh": 0.10,
        "new_track_thresh": 0.50,
        "match_thresh": 0.80,
    })
    assert resp.status_code == 422


def test_settings_rejects_invalid_threshold(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 1.5,
        "iou_threshold": 0.60,
        "track_memory_minutes": 240,
        "track_high_thresh": 0.50,
        "track_low_thresh": 0.10,
        "new_track_thresh": 0.50,
        "match_thresh": 0.80,
    })
    assert resp.status_code == 422
```

Then append these 3 new tests:

```python
def test_settings_accepts_tracker_params(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 0.65,
        "iou_threshold": 0.60,
        "track_memory_minutes": 120,
        "track_high_thresh": 0.55,
        "track_low_thresh": 0.12,
        "new_track_thresh": 0.55,
        "match_thresh": 0.75,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_settings_rejects_invalid_track_memory(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 0.65,
        "iou_threshold": 0.60,
        "track_memory_minutes": 9999,
        "track_high_thresh": 0.5,
        "track_low_thresh": 0.1,
        "new_track_thresh": 0.5,
        "match_thresh": 0.8,
    })
    assert resp.status_code == 422


def test_settings_tracker_change_triggers_restart(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 0.65,
        "iou_threshold": 0.60,
        "track_memory_minutes": 60,
        "track_high_thresh": 0.5,
        "track_low_thresh": 0.1,
        "new_track_thresh": 0.5,
        "match_thresh": 0.8,
    })
    assert resp.status_code == 200
    assert resp.json()["restarted"] is True
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m pytest tests/test_integration.py::test_settings_accepts_tracker_params tests/test_integration.py::test_settings_rejects_invalid_track_memory tests/test_integration.py::test_settings_tracker_change_triggers_restart -v
```

Expected: all 3 FAIL

- [ ] **Step 3: Update the `update_settings` function in `main.py`**

Replace the entire `update_settings` function:

```python
@app.post("/control/settings")
async def update_settings(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    model_name = body.get("model_name")
    confidence_threshold = body.get("confidence_threshold")
    iou_threshold = body.get("iou_threshold")
    track_memory_minutes = body.get("track_memory_minutes")
    track_high_thresh = body.get("track_high_thresh")
    track_low_thresh = body.get("track_low_thresh")
    new_track_thresh = body.get("new_track_thresh")
    match_thresh = body.get("match_thresh")

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
    if not isinstance(track_memory_minutes, int) or not (1 <= track_memory_minutes <= 1440):
        return JSONResponse(
            {"error": "track_memory_minutes must be an int between 1 and 1440"},
            status_code=422,
        )
    if not isinstance(track_high_thresh, (int, float)) or not (0.1 <= track_high_thresh <= 0.99):
        return JSONResponse(
            {"error": "track_high_thresh must be a float between 0.1 and 0.99"},
            status_code=422,
        )
    if not isinstance(track_low_thresh, (int, float)) or not (0.05 <= track_low_thresh < track_high_thresh):
        return JSONResponse(
            {"error": "track_low_thresh must be a float between 0.05 and track_high_thresh"},
            status_code=422,
        )
    if not isinstance(new_track_thresh, (int, float)) or not (0.1 <= new_track_thresh <= 0.99):
        return JSONResponse(
            {"error": "new_track_thresh must be a float between 0.1 and 0.99"},
            status_code=422,
        )
    if not isinstance(match_thresh, (int, float)) or not (0.1 <= match_thresh <= 0.99):
        return JSONResponse(
            {"error": "match_thresh must be a float between 0.1 and 0.99"},
            status_code=422,
        )

    model_changed = model_name != state.model_name
    tracker_changed = (
        track_memory_minutes != state.track_memory_minutes
        or track_high_thresh != state.track_high_thresh
        or track_low_thresh != state.track_low_thresh
        or new_track_thresh != state.new_track_thresh
        or match_thresh != state.match_thresh
    )

    state.update(
        model_name=model_name,
        confidence_threshold=float(confidence_threshold),
        iou_threshold=float(iou_threshold),
        track_memory_minutes=int(track_memory_minutes),
        track_high_thresh=float(track_high_thresh),
        track_low_thresh=float(track_low_thresh),
        new_track_thresh=float(new_track_thresh),
        match_thresh=float(match_thresh),
    )

    restarted = False
    if model_changed or tracker_changed:
        global _detector_stop
        _detector_stop.set()
        _detector_stop = threading.Event()
        reason = f"Model changed to {model_name}" if model_changed else "Tracker params changed"
        log_buffer.append("detector", "INFO", f"{reason}, restarting")
        threading.Thread(
            target=run_detector,
            args=(state, _detector_stop),
            daemon=True,
        ).start()
        restarted = True

    return JSONResponse({"status": "ok", "restarted": restarted})
```

- [ ] **Step 4: Run all integration tests**

```bash
python3 -m pytest tests/test_integration.py -q
```

Expected: all 19 PASS in under 5s (same count — 3 existing tests updated + 3 new = net +3)

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -q
```

Expected: all 54 PASS in under 10s

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "feat: extend settings endpoint with 5 tracker params, restart on tracker change"
```

---

### Task 4: Update `monitor.py` + monitor tests — pass through tracker fields

**Files:**
- Modify: `monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_monitor.py`:

```python
def test_get_settings_returns_tracker_fields(client):
    data = client.get("/api/settings").json()
    assert "track_memory_minutes" in data
    assert "track_high_thresh" in data
    assert "track_low_thresh" in data
    assert "new_track_thresh" in data
    assert "match_thresh" in data
    assert data["track_memory_minutes"] == 240
    assert data["match_thresh"] == 0.8
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_monitor.py::test_get_settings_returns_tracker_fields -v
```

Expected: FAIL — tracker fields missing from response

- [ ] **Step 3: Update `get_settings` in `monitor.py`**

Replace the entire `get_settings` function:

```python
@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    return JSONResponse({
        "model_name": _state.last_health.get("model_name", "yolov8s.pt"),
        "confidence_threshold": _state.last_health.get("confidence_threshold", 0.65),
        "iou_threshold": _state.last_health.get("iou_threshold", 0.60),
        "track_memory_minutes": _state.last_health.get("track_memory_minutes", 240),
        "track_high_thresh": _state.last_health.get("track_high_thresh", 0.5),
        "track_low_thresh": _state.last_health.get("track_low_thresh", 0.1),
        "new_track_thresh": _state.last_health.get("new_track_thresh", 0.5),
        "match_thresh": _state.last_health.get("match_thresh", 0.8),
    })
```

- [ ] **Step 4: Run all monitor tests**

```bash
python3 -m pytest tests/test_monitor.py -v
```

Expected: all 12 PASS

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -q
```

Expected: all 55 PASS in under 10s

- [ ] **Step 6: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat: return all 8 settings fields from monitor GET /api/settings"
```

---

### Task 5: Redesign DETECTION panel in `monitor_static/index.html`

**Files:**
- Modify: `monitor_static/index.html`

No automated tests. Manual verification steps at end.

- [ ] **Step 1: Add new CSS**

Inside the `<style>` block, add before the closing `</style>`:

```css
        .settings-group { margin-bottom: 1rem; }
        .settings-label { font-size: 0.8rem; color: #888; margin-bottom: 0.4rem; }
        .settings-hint { color: #555; font-size: 0.7rem; margin-left: 0.5rem; font-style: italic; }
        .settings-sublabel { font-size: 0.7rem; color: #555; margin-bottom: 0.25rem; margin-top: 0.4rem; }
        .preset-row { display: flex; gap: 0.4rem; flex-wrap: wrap; }
        .preset-btn { background: #1e1e1e; border: 1px solid #333; color: #666; padding: 0.25rem 0.6rem; cursor: pointer; font-family: monospace; font-size: 0.75rem; }
        .preset-btn.active { border-color: #4caf50; color: #4caf50; }
        .preset-btn:hover { background: #2a2a2a; }
        .model-cards { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .model-card { background: #1a1a1a; border: 1px solid #333; padding: 0.5rem 0.75rem; cursor: pointer; font-family: monospace; font-size: 0.8rem; display: flex; flex-direction: column; gap: 0.15rem; }
        .model-card.selected { border-color: #4caf50; }
        .model-name { color: #ccc; }
        .model-desc { color: #555; font-size: 0.7rem; }
        input[type="range"] { accent-color: #4caf50; width: 100%; }
```

- [ ] **Step 2: Replace the entire DETECTION section HTML**

Find and replace from `<div class="section-title" style="margin-top:1.5rem;margin-bottom:0.75rem">DETECTION</div>` through the Apply button `</div>` (the closing div of the settings group containing Apply):

```html
        <div class="section-title" style="margin-top:1.5rem;margin-bottom:0.75rem">DETECTION</div>
        <div class="settings-group">
            <div class="settings-label">Presets</div>
            <div class="preset-row" id="det-presets">
                <button class="preset-btn" onclick="setDetPreset('fast',event)">Fast</button>
                <button class="preset-btn active" onclick="setDetPreset('balanced',event)">Balanced</button>
                <button class="preset-btn" onclick="setDetPreset('accurate',event)">Accurate ⚠</button>
                <button class="preset-btn" id="det-custom-btn" style="display:none" onclick="">Custom</button>
            </div>
        </div>
        <div class="settings-group">
            <div class="settings-label">Model</div>
            <div class="model-cards" id="model-cards">
                <div class="model-card" data-model="yolov8n.pt" onclick="selectModel('yolov8n.pt')">
                    <span class="model-name">yolov8n</span>
                    <span class="model-desc">Fast, less accurate</span>
                </div>
                <div class="model-card selected" data-model="yolov8s.pt" onclick="selectModel('yolov8s.pt')">
                    <span class="model-name">yolov8s</span>
                    <span class="model-desc">Recommended ✓</span>
                </div>
                <div class="model-card" data-model="yolov8m.pt" onclick="selectModel('yolov8m.pt')">
                    <span class="model-name">yolov8m</span>
                    <span class="model-desc">Accurate ⚠ hot</span>
                </div>
            </div>
        </div>
        <div class="settings-group">
            <div class="settings-label">Confidence <span class="settings-hint">Permissive ←→ Strict</span></div>
            <div style="display:flex;align-items:center;gap:0.75rem">
                <input id="setting-confidence" type="range" min="0.10" max="0.99" step="0.05" value="0.65" oninput="markDetCustom();document.getElementById('conf-val').textContent=parseFloat(this.value).toFixed(2)">
                <span id="conf-val" style="width:2.5rem;text-align:right;font-size:0.85rem;color:#ccc">0.65</span>
            </div>
        </div>
        <div class="settings-group">
            <div class="settings-label">IoU <span class="settings-hint">Permissive ←→ Strict</span></div>
            <div style="display:flex;align-items:center;gap:0.75rem">
                <input id="setting-iou" type="range" min="0.10" max="0.99" step="0.05" value="0.60" oninput="markDetCustom();document.getElementById('iou-val').textContent=parseFloat(this.value).toFixed(2)">
                <span id="iou-val" style="width:2.5rem;text-align:right;font-size:0.85rem;color:#ccc">0.60</span>
            </div>
        </div>

        <div class="section-title" style="margin-top:1.5rem;margin-bottom:0.75rem">TRACKING</div>
        <div class="settings-group">
            <div class="settings-label">Presets</div>
            <div class="preset-row" id="trk-presets">
                <button class="preset-btn active" onclick="setTrkPreset('busy',event)">Busy Event</button>
                <button class="preset-btn" onclick="setTrkPreset('quiet',event)">Quiet Room</button>
                <button class="preset-btn" onclick="setTrkPreset('strict',event)">Strict</button>
                <button class="preset-btn" id="trk-custom-btn" style="display:none" onclick="">Custom</button>
            </div>
        </div>
        <div class="settings-group">
            <div class="settings-label">Track Memory <span class="settings-hint">How long to remember a person after leaving frame</span></div>
            <div style="display:flex;align-items:center;gap:0.75rem">
                <input id="setting-track-memory" type="number" min="1" max="1440" step="1" value="240" class="log-select" style="width:70px" oninput="markTrkCustom();updateMemoryHint()">
                <span id="memory-hint" style="font-size:0.75rem;color:#555">≈ 4 hours</span>
            </div>
        </div>
        <div class="settings-group">
            <div class="settings-label">Confidence Zones <span class="settings-hint">ignored / recovery only / actively tracked</span></div>
            <div id="zone-bar" style="height:10px;border-radius:3px;margin-bottom:0.75rem;background:#333"></div>
            <div class="settings-sublabel">Low threshold — ignored → recovery (must be &lt; High)</div>
            <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem">
                <input id="setting-low-thresh" type="range" min="0.05" max="0.49" step="0.05" value="0.10" oninput="markTrkCustom();updateZoneBar();document.getElementById('low-val').textContent=parseFloat(this.value).toFixed(2)">
                <span id="low-val" style="width:2.5rem;text-align:right;font-size:0.85rem;color:#ccc">0.10</span>
            </div>
            <div class="settings-sublabel">High threshold — recovery → actively tracked</div>
            <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem">
                <input id="setting-high-thresh" type="range" min="0.10" max="0.99" step="0.05" value="0.50" oninput="markTrkCustom();updateZoneBar();document.getElementById('high-val').textContent=parseFloat(this.value).toFixed(2)">
                <span id="high-val" style="width:2.5rem;text-align:right;font-size:0.85rem;color:#ccc">0.50</span>
            </div>
            <div class="settings-sublabel">New person threshold — min confidence to register a brand new person</div>
            <div style="display:flex;align-items:center;gap:0.75rem">
                <input id="setting-new-track-thresh" type="range" min="0.10" max="0.99" step="0.05" value="0.50" oninput="markTrkCustom();document.getElementById('new-val').textContent=parseFloat(this.value).toFixed(2)">
                <span id="new-val" style="width:2.5rem;text-align:right;font-size:0.85rem;color:#ccc">0.50</span>
            </div>
        </div>
        <div class="settings-group">
            <div class="settings-label">Re-ID Match Strictness <span class="settings-hint">Loose ←→ Strict — overlap required to recognise returning person</span></div>
            <div style="display:flex;align-items:center;gap:0.75rem">
                <input id="setting-match-thresh" type="range" min="0.10" max="0.99" step="0.05" value="0.80" oninput="markTrkCustom();document.getElementById('match-val').textContent=parseFloat(this.value).toFixed(2)">
                <span id="match-val" style="width:2.5rem;text-align:right;font-size:0.85rem;color:#ccc">0.80</span>
            </div>
        </div>
        <div style="display:flex;align-items:center;gap:1rem;margin-top:1rem">
            <button class="btn" onclick="applySettings()">Apply</button>
            <span id="settings-status" style="font-size:0.8rem;color:#4caf50"></span>
        </div>
```

- [ ] **Step 3: Replace `loadSettings()`, `applySettings()`, and add new JS functions**

Replace the entire `loadSettings` and `applySettings` functions, and add the new preset/helper functions. Find `function loadSettings()` and replace everything through the end of `applySettings()`:

```js
        var _DET_PRESETS = {
            fast:     { model: 'yolov8n.pt', confidence: 0.50, iou: 0.45 },
            balanced: { model: 'yolov8s.pt', confidence: 0.65, iou: 0.60 },
            accurate: { model: 'yolov8m.pt', confidence: 0.75, iou: 0.65 },
        };
        var _TRK_PRESETS = {
            busy:   { memory: 240, high: 0.50, low: 0.10, newt: 0.50, match: 0.80 },
            quiet:  { memory: 60,  high: 0.60, low: 0.15, newt: 0.60, match: 0.85 },
            strict: { memory: 30,  high: 0.70, low: 0.20, newt: 0.70, match: 0.90 },
        };

        function selectModel(model) {
            document.querySelectorAll('.model-card').forEach(function(c) {
                c.classList.toggle('selected', c.dataset.model === model);
            });
            markDetCustom();
        }

        function setDetPreset(name, evt) {
            var p = _DET_PRESETS[name];
            document.querySelectorAll('.model-card').forEach(function(c) {
                c.classList.toggle('selected', c.dataset.model === p.model);
            });
            document.getElementById('setting-confidence').value = p.confidence;
            document.getElementById('setting-iou').value = p.iou;
            document.getElementById('conf-val').textContent = p.confidence.toFixed(2);
            document.getElementById('iou-val').textContent = p.iou.toFixed(2);
            document.querySelectorAll('#det-presets .preset-btn').forEach(function(b) { b.classList.remove('active'); });
            if (evt && evt.target) evt.target.classList.add('active');
            document.getElementById('det-custom-btn').style.display = 'none';
        }

        function markDetCustom() {
            document.querySelectorAll('#det-presets .preset-btn:not(#det-custom-btn)').forEach(function(b) { b.classList.remove('active'); });
            var cb = document.getElementById('det-custom-btn');
            cb.style.display = 'inline-block';
            cb.classList.add('active');
        }

        function setTrkPreset(name, evt) {
            var p = _TRK_PRESETS[name];
            document.getElementById('setting-track-memory').value = p.memory;
            document.getElementById('setting-high-thresh').value = p.high;
            document.getElementById('setting-low-thresh').value = p.low;
            document.getElementById('setting-new-track-thresh').value = p.newt;
            document.getElementById('setting-match-thresh').value = p.match;
            document.getElementById('high-val').textContent = p.high.toFixed(2);
            document.getElementById('low-val').textContent = p.low.toFixed(2);
            document.getElementById('new-val').textContent = p.newt.toFixed(2);
            document.getElementById('match-val').textContent = p.match.toFixed(2);
            updateMemoryHint();
            updateZoneBar();
            document.querySelectorAll('#trk-presets .preset-btn').forEach(function(b) { b.classList.remove('active'); });
            if (evt && evt.target) evt.target.classList.add('active');
            document.getElementById('trk-custom-btn').style.display = 'none';
        }

        function markTrkCustom() {
            document.querySelectorAll('#trk-presets .preset-btn:not(#trk-custom-btn)').forEach(function(b) { b.classList.remove('active'); });
            var cb = document.getElementById('trk-custom-btn');
            cb.style.display = 'inline-block';
            cb.classList.add('active');
        }

        function updateMemoryHint() {
            var mins = parseInt(document.getElementById('setting-track-memory').value) || 0;
            var hint = mins >= 60
                ? '≈ ' + (mins / 60).toFixed(1).replace(/\.0$/, '') + ' hour' + (mins === 60 ? '' : 's')
                : mins + ' min' + (mins === 1 ? '' : 's');
            document.getElementById('memory-hint').textContent = hint;
        }

        function updateZoneBar() {
            var low = parseFloat(document.getElementById('setting-low-thresh').value);
            var high = parseFloat(document.getElementById('setting-high-thresh').value);
            var l = (low * 100).toFixed(0), h = (high * 100).toFixed(0);
            document.getElementById('zone-bar').style.background =
                'linear-gradient(to right,#333 0%,#333 ' + l + '%,rgba(255,152,0,0.5) ' + l + '%,rgba(255,152,0,0.5) ' + h + '%,rgba(76,175,80,0.5) ' + h + '%,rgba(76,175,80,0.5) 100%)';
        }

        function loadSettings() {
            fetch('/api/settings')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var model = d.model_name || 'yolov8s.pt';
                    document.querySelectorAll('.model-card').forEach(function(c) {
                        c.classList.toggle('selected', c.dataset.model === model);
                    });
                    var conf = d.confidence_threshold || 0.65;
                    var iou = d.iou_threshold || 0.60;
                    document.getElementById('setting-confidence').value = conf;
                    document.getElementById('setting-iou').value = iou;
                    document.getElementById('conf-val').textContent = parseFloat(conf).toFixed(2);
                    document.getElementById('iou-val').textContent = parseFloat(iou).toFixed(2);

                    document.getElementById('setting-track-memory').value = d.track_memory_minutes || 240;
                    document.getElementById('setting-high-thresh').value = d.track_high_thresh || 0.50;
                    document.getElementById('setting-low-thresh').value = d.track_low_thresh || 0.10;
                    document.getElementById('setting-new-track-thresh').value = d.new_track_thresh || 0.50;
                    document.getElementById('setting-match-thresh').value = d.match_thresh || 0.80;
                    document.getElementById('high-val').textContent = parseFloat(d.track_high_thresh || 0.50).toFixed(2);
                    document.getElementById('low-val').textContent = parseFloat(d.track_low_thresh || 0.10).toFixed(2);
                    document.getElementById('new-val').textContent = parseFloat(d.new_track_thresh || 0.50).toFixed(2);
                    document.getElementById('match-val').textContent = parseFloat(d.match_thresh || 0.80).toFixed(2);
                    updateMemoryHint();
                    updateZoneBar();
                })
                .catch(function() {});
        }

        function applySettings() {
            var selectedCard = document.querySelector('.model-card.selected');
            var modelName = selectedCard ? selectedCard.dataset.model : 'yolov8s.pt';
            var statusEl = document.getElementById('settings-status');
            statusEl.textContent = 'Applying…';
            statusEl.style.color = '#888';
            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_name: modelName,
                    confidence_threshold: parseFloat(document.getElementById('setting-confidence').value),
                    iou_threshold: parseFloat(document.getElementById('setting-iou').value),
                    track_memory_minutes: parseInt(document.getElementById('setting-track-memory').value),
                    track_high_thresh: parseFloat(document.getElementById('setting-high-thresh').value),
                    track_low_thresh: parseFloat(document.getElementById('setting-low-thresh').value),
                    new_track_thresh: parseFloat(document.getElementById('setting-new-track-thresh').value),
                    match_thresh: parseFloat(document.getElementById('setting-match-thresh').value),
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

- [ ] **Step 4: Initialise zone bar on page load**

In the boot IIFE at the bottom of the script (the `(function() {` block), add `updateZoneBar();` after the tab activation:

```js
        (function() {
            var saved = localStorage.getItem('pi-monitor-tab') || 'live';
            if (saved === 'live') {
                startLive();
            } else {
                document.getElementById('tab-live').classList.remove('active');
                document.getElementById('tab-ops').classList.add('active');
                document.querySelectorAll('.tab-btn')[0].classList.remove('active');
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                currentTab = 'ops';
                startOps();
            }
            updateZoneBar();
        })();
```

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest -q
```

Expected: all 55 PASS in under 10s

- [ ] **Step 6: Manual verification**

```bash
MOCK_CAMERA=1 uvicorn main:app --port 8000 &
uvicorn monitor:app --port 8001
```

Open `http://localhost:8001` → OPS tab:
- DETECTION section shows preset buttons, model cards (clickable), confidence + IoU sliders with live values
- TRACKING section shows preset buttons, track memory input with hint, zone bar updating as sliders move, Re-ID slider
- Selecting "Balanced" preset highlights the correct model card and sets confidence/IoU
- Selecting "Quiet Room" tracking preset fills all tracking fields
- Apply shows "Applied — detector restarting…"

- [ ] **Step 7: Commit**

```bash
git add monitor_static/index.html
git commit -m "feat: redesign DETECTION panel with presets, model cards, and confidence zone visualiser"
```
