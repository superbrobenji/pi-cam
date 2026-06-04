# Tracker Settings & Detection Panel Redesign

**Date:** 2026-06-04

## Problem

1. ByteTrack's default `track_buffer=30` (30 frames) is designed for 30 FPS video. At 1 FPS this is only 30 seconds of track memory — causing the same person to be counted as "first seen" repeatedly at event floors.
2. All tracker parameters are hardcoded. The DETECTION dashboard panel uses plain number inputs with no context, presets, or visual aids.

## Goals

- Fix the tracker false-positive root cause: `track_buffer` defaults to 14,400 (4 hours at 1 FPS)
- Add 5 configurable ByteTrack parameters (track memory, confidence zones, re-ID strictness)
- Redesign the DETECTION panel with presets + visual inputs for both detection and tracking settings

## Out of Scope

- BoTSORT or other trackers
- Per-camera profiles

---

## Design

### New SharedState fields

Five new tracker fields (all require detector restart when changed):

| Field | Type | Default | Description |
|---|---|---|---|
| `track_memory_minutes` | `int` | `240` | Track buffer in minutes (converted to frames × 60 in YAML) |
| `track_high_thresh` | `float` | `0.5` | Detections above this are actively tracked |
| `track_low_thresh` | `float` | `0.1` | Detections between low and high recover lost tracks, don't start new ones |
| `new_track_thresh` | `float` | `0.5` | Min confidence to register a brand new person |
| `match_thresh` | `float` | `0.8` | IoU overlap required to match a re-appearing detection to a known track |

All five included in `snapshot()`.

### `bytetrack.yaml` (new file)

Written by `_run_live_loop` before model load, from current SharedState values:

```yaml
tracker_type: bytetrack
track_high_thresh: {state.track_high_thresh}
track_low_thresh: {state.track_low_thresh}
new_track_thresh: {state.new_track_thresh}
track_buffer: {state.track_memory_minutes * 60}
match_thresh: {state.match_thresh}
```

`model.track(..., tracker="bytetrack.yaml")` reads this file. Re-written on detector restart whenever tracker params change.

### `detector.py` changes

- At start of `_run_live_loop` (before YOLO load), write `bytetrack.yaml` from current state values
- Pass `tracker="bytetrack.yaml"` to `model.track()`
- Mock loop unchanged (no tracker in mock mode)

### `main.py` `/control/settings` changes

Accept 5 new optional fields alongside existing 3. Validation:
- `track_memory_minutes`: int, 1–1440 (1 min to 24 hours)
- `track_high_thresh`: float, 0.1–0.99, must be > `track_low_thresh`
- `track_low_thresh`: float, 0.05–0.5, must be < `track_high_thresh`
- `new_track_thresh`: float, 0.1–0.99
- `match_thresh`: float, 0.1–0.99

Any change to any tracker param → set `tracker_changed = True` → restart detector (same as model change). `restarted` in response reflects this.

### `monitor.py`

`GET /api/settings` passes through all 8 fields from health snapshot.
`POST /api/settings` proxies all 8 fields unchanged.

### Dashboard DETECTION panel redesign

Two sub-sections: **Detection** and **Tracking**. Presets at top of each. Apply button at bottom of panel applies both sections and restarts detector.

#### Detection sub-section

**Presets:** Fast | Balanced (default ✓) | Accurate ⚠ | Custom

| Preset | model_name | confidence_threshold | iou_threshold |
|---|---|---|---|
| Fast | yolov8n.pt | 0.50 | 0.45 |
| Balanced | yolov8s.pt | 0.65 | 0.60 |
| Accurate | yolov8m.pt | 0.75 | 0.65 |

**Model selector:** three radio-style cards:
- `yolov8n` — Fast, less accurate
- `yolov8s` — Recommended ✓
- `yolov8m` — Most accurate, runs hot ⚠

**Confidence:** labeled range slider, "Permissive ←→ Strict", value shown.

**IoU:** labeled range slider, "Permissive ←→ Strict", value shown.

#### Tracking sub-section

**Presets:** Busy Event (default ✓) | Quiet Room | Strict | Custom

| Preset | memory | high | low | new | match |
|---|---|---|---|---|---|
| Busy Event | 240 | 0.5 | 0.1 | 0.5 | 0.80 |
| Quiet Room | 60 | 0.6 | 0.15 | 0.6 | 0.85 |
| Strict | 30 | 0.7 | 0.2 | 0.7 | 0.90 |

**Track Memory:** number input (minutes) + helper text `≈ X hours/minutes`.

**Confidence Zones:** visual bar with 3 draggable handles (low_thresh, high_thresh, new_track_thresh):
```
[─── ignored ──|── recovery ──|── tracked ───]
0.0          low            high            1.0
                                   ↑ new_track marker
```
Handles snap to 0.05 increments. low must stay < high.

**Re-ID Match:** labeled range slider, "Loose ←→ Strict".

#### Behaviour

- Selecting a preset populates all fields in its section
- Editing any field → current preset switches to "Custom"
- "Apply" button at bottom validates + POSTs to `/api/settings` with all 8 fields
- Success: shows "Applied — detector restarting…" if any of the 5 tracker params or `model_name` changed; shows "Applied" if only `confidence_threshold` or `iou_threshold` changed (those are read live from state, no restart needed)

---

## Files Changed

| File | Action |
|---|---|
| `bytetrack.yaml` | Create — written by detector at startup |
| `shared_state.py` | Add 5 tracker fields |
| `detector.py` | Write bytetrack.yaml, pass `tracker=` param |
| `main.py` | Extend `/control/settings` validation + restart logic |
| `monitor.py` | Pass through all 8 fields in GET/POST |
| `monitor_static/index.html` | Full DETECTION panel redesign |
| `tests/test_shared_state.py` | Assert 5 new fields |
| `tests/test_integration.py` | Test settings with tracker params |
