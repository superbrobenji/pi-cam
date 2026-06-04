# Unique People Tracking Design

**Date:** 2026-06-04

## Problem

The WebSocket currently emits `{"count": N}` — total people visible in the current frame. This tells you how many people are present right now but nothing about whether they are new arrivals or returning faces. There is no way to distinguish "same 5 people still in frame" from "5 new people just entered."

## Goals

- Rename `count` to `rawCount` in the WebSocket payload
- Add `enteredFrame` — people not present in the previous tick (re-entry counts again)
- Add `firstSeen` — people appearing for the first time ever in this session
- Add `uniqueTotal` — cumulative count of all unique individuals seen since app start
- Display all four fields on the LIVE dashboard tab

## Out of Scope

- Persistent identity across app restarts
- Named/labelled individuals
- Face recognition

---

## Design

### Tracking approach

Switch `_run_live_loop` in `detector.py` from `model(frame)` to `model.track(frame, persist=True)`. YOLOv8's built-in ByteTrack assigns a persistent integer ID to each tracked person that follows them across frames. This is the authoritative source for "same person / different person."

Two private sets maintained inside `_run_live_loop`:
- `_prev_ids: set[int]` — IDs detected in the previous tick (reset to empty on first tick)
- `_all_seen_ids: set[int]` — every ID ever detected since the detector started (never shrinks)

Per-tick calculation:
```python
ids = set(results.boxes.id.int().tolist()) if results.boxes.id is not None else set()
entered_frame  = len(ids - _prev_ids)
new_ids        = ids - _all_seen_ids
_all_seen_ids.update(ids)
_prev_ids = ids
state.update(
    count=len(ids),
    entered_frame=entered_frame,
    first_seen=len(new_ids),
    unique_total=len(_all_seen_ids),
)
```

`results.boxes.id` can be `None` when no people are detected or tracking initialises. Guard with `if results.boxes.id is not None else set()`.

**Mock mode:** `_run_mock_loop` sets `entered_frame=0`, `first_seen=0`, `unique_total=0` — no tracking in mock mode.

**On restart:** Both sets are local to `_run_live_loop`, so they reset on detector thread restart. `unique_total` returns to 0.

### `shared_state.py`

Three new integer fields, all initialised to 0, included in `snapshot()`:

| Field | Type | Description |
|---|---|---|
| `entered_frame` | `int` | People not in previous tick |
| `first_seen` | `int` | People seen for first time this session |
| `unique_total` | `int` | Cumulative unique people since start |

### WebSocket payload

`main.py` `websocket_endpoint` changes send from:
```json
{"count": 5}
```
to:
```json
{
  "rawCount": 5,
  "enteredFrame": 2,
  "firstSeen": 1,
  "uniqueTotal": 14
}
```

`rawCount` maps from `state.count`. The three new fields map from the three new SharedState fields.

### LIVE dashboard tab

Replace the single large count display with four stat cards in a 2×2 grid:

| Card | Field | Label |
|---|---|---|
| Top-left | `rawCount` | IN FRAME |
| Top-right | `enteredFrame` | ENTERED |
| Bottom-left | `firstSeen` | FIRST SEEN |
| Bottom-right | `uniqueTotal` | TOTAL UNIQUE |

Cards use the same `health-card` style already in the dashboard. The existing health stats grid (CPU/RAM/TEMP/DISK) moves below the people grid.

The WebSocket `onmessage` handler in the dashboard is updated to read all four fields.

A "Reset Unique Count" button appears below the people grid. Clicking it shows `confirm("Reset unique total? This cannot be undone.")`. On confirm, the dashboard POSTs to `/api/reset-tracking` on the monitor (port 8001), which proxies to `POST /control/reset-tracking` on the main app (port 8000). Routing through the monitor avoids browser CORS restrictions.

### Reset mechanism

`SharedState` gains a `reset_tracking: bool` field (init `False`). The detector checks it at the top of each iteration:

```python
if state.reset_tracking:
    _prev_ids.clear()
    _all_seen_ids.clear()
    state.update(reset_tracking=False, unique_total=0, first_seen=0, entered_frame=0)
```

`POST /control/reset-tracking` on the main app sets `state.update(reset_tracking=True)`.  
`POST /api/reset-tracking` on the monitor proxies to `:8000/control/reset-tracking`.

Reset applies to live mode only. Mock mode ignores `reset_tracking` since tracking fields are always 0.

---

## Files Changed

| File | Change |
|---|---|
| `shared_state.py` | Add `entered_frame`, `first_seen`, `unique_total`, `reset_tracking` to `_FIELDS`, `__init__`, `snapshot()` |
| `detector.py` | Switch to `model.track()`, compute all four values, check `reset_tracking` flag each tick; mock loop adds zero values |
| `main.py` | WebSocket sends all four fields; add `POST /control/reset-tracking` endpoint |
| `monitor.py` | Add `POST /api/reset-tracking` proxy endpoint |
| `monitor_static/index.html` | Replace single count with 4-card grid; update WS handler; add Reset button with confirm |
| `tests/test_shared_state.py` | Add assertions for four new fields |
| `tests/test_integration.py` | Update WebSocket test; add reset endpoint test |
| `tests/test_monitor.py` | Add reset proxy endpoint test |
| `tests/test_detector.py` | Update frame/count assertions; mock returns 0 for tracking fields |
