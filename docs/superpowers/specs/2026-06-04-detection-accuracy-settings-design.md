# Detection Accuracy & Settings Design

**Date:** 2026-06-04

## Problem

`yolov8n` (nano) produces false positives and double-counts people at event floors where lighting varies and people partially overlap. Detection parameters (confidence threshold, NMS IoU, model) are hardcoded and require code changes to tune. The WebSocket sends at a fixed 1s interval regardless of whether the model has produced a new result, causing stale data sends with slower models.

## Goals

- Upgrade default model from `yolov8n` to `yolov8s` for meaningfully better accuracy in dynamic environments
- Make model, confidence threshold, and IoU threshold configurable at runtime via dashboard
- WebSocket sends are event-driven: fires only when a new inference result is available, with a 1s minimum floor to prevent flooding slow consumers
- OPS tab exposes a DETECTION settings panel with model selector and threshold inputs

## Out of Scope

- Hardware acceleration (Hailo, CUDA)
- Per-camera profiles
- Model fine-tuning or custom training

---

## Design

### `shared_state.py` additions

Four new fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `model_name` | `str` | `"yolov8s.pt"` | Active YOLO model filename |
| `confidence_threshold` | `float` | `0.65` | Minimum detection confidence (0.1–0.99) |
| `iou_threshold` | `float` | `0.60` | NMS IoU threshold (0.1–0.99) |
| `inference_tick` | `int` | `0` | Incremented after every successful inference; visible in `/health` for external monitoring |

All four included in `snapshot()`.

### `detector.py` changes

**Signature:** `run_detector(state, stop_event, on_inference=None)` — new optional `on_inference: Optional[Callable]` callback called after each successful inference (both mock and live loops).

**Model load:** reads `state.model_name` once at start of `_run_live_loop`. Model default is effectively `"yolov8s.pt"` via SharedState default.

**Per-tick thresholds:** reads `state.confidence_threshold` and `state.iou_threshold` from SharedState each iteration — changes take effect on next tick without restart.

**Tracking call:** passes `iou` to tracker:
```python
results = model.track(frame, persist=True, verbose=False, iou=state.iou_threshold)[0]
```

**Confidence filter:** uses `state.confidence_threshold` instead of hardcoded `_CONFIDENCE_THRESHOLD`.

**Mock loop:** calls `on_inference()` each iteration so WS fires at ~1 FPS in mock mode.

**Live loop:** calls `on_inference()` after each successful state update.

**`inference_tick`:** incremented in both loops via `state.update(inference_tick=state.inference_tick + 1, ...)`.

**Remove:** `_CONFIDENCE_THRESHOLD = 0.5` module-level constant (now read from state).

### `main.py` changes

**Inference event machinery:**

```python
_inference_event = asyncio.Event()
_event_loop: Optional[asyncio.AbstractEventLoop] = None
```

Set `_event_loop = asyncio.get_running_loop()` in lifespan. Pass callback to detector:

```python
def _on_inference():
    _event_loop.call_soon_threadsafe(_inference_event.set)

threading.Thread(target=run_detector, args=(state, _detector_stop, _on_inference), daemon=True).start()
```

**WebSocket loop** — replace fixed `asyncio.sleep(1.0)` with event-driven send:

```python
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
```

**`POST /control/settings`** endpoint:

- Accepts `{model_name, confidence_threshold, iou_threshold}`
- Validates: `model_name` in `{"yolov8n.pt", "yolov8s.pt", "yolov8m.pt"}`; thresholds are floats in range [0.1, 0.99]
- Returns 422 on validation failure with error message
- Updates SharedState with validated values
- If `model_name` changed → sets `_detector_stop`, creates new event, starts new detector thread
- Returns `{"status": "ok", "restarted": True/False}`

**Restart also updates callback:** new thread gets new `_on_inference` callback referencing current `_event_loop` and `_inference_event`.

### `monitor.py` changes

**`GET /api/settings`** — returns settings from cached health snapshot:

```python
@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    return JSONResponse({
        "model_name": _state.last_health.get("model_name", "yolov8s.pt"),
        "confidence_threshold": _state.last_health.get("confidence_threshold", 0.65),
        "iou_threshold": _state.last_health.get("iou_threshold", 0.60),
    })
```

**`POST /api/settings`** — proxies to `:8000/control/settings`:
- Returns 503 if offline
- Returns proxied response otherwise

### `monitor_static/index.html` — DETECTION section (OPS tab)

New section at bottom of OPS tab, loaded when tab opens:

```
DETECTION

Model       [ yolov8n  ▼ ]  (options: yolov8n, yolov8s, yolov8m ⚠ runs hot)
Confidence  [ 0.65 ]
IoU         [ 0.60 ]
                                        [Apply]
```

- `loadSettings()` called in `startOps()` — populates inputs from `GET /api/settings`
- "Apply" button calls `applySettings()`: POSTs to `/api/settings`, shows "Applied" or "Restarting detector…" based on `restarted` field in response
- Inputs: model is `<select>`, thresholds are `<input type="number" step="0.05" min="0.1" max="0.99">`
- Medium option label: `yolov8m.pt (⚠ runs hot)`

---

## Performance notes

| Model | Inference | Effective WS rate | Pi 5 CPU temp |
|---|---|---|---|
| `yolov8n.pt` | ~150ms | 1 FPS (floor) | moderate |
| `yolov8s.pt` | ~400ms | 1 FPS (floor) | warm |
| `yolov8m.pt` | ~900ms–1.5s | ~0.7 FPS | hot (75–85°C) |

---

## Files changed

| File | Change |
|---|---|
| `shared_state.py` | Add `model_name`, `confidence_threshold`, `iou_threshold`, `inference_tick` |
| `detector.py` | `on_inference` callback, read thresholds from state, remove constant, increment tick |
| `main.py` | `_inference_event`, event-driven WS, `POST /control/settings` |
| `monitor.py` | `GET /api/settings`, `POST /api/settings` |
| `monitor_static/index.html` | DETECTION settings panel, `loadSettings()`, `applySettings()` |
| `tests/test_shared_state.py` | Assert 4 new fields |
| `tests/test_detector.py` | Test `on_inference` callback fires; mock sets `inference_tick > 0` |
| `tests/test_integration.py` | Test settings endpoint validation + response |
| `tests/test_monitor.py` | Test settings proxy 503 when offline |
