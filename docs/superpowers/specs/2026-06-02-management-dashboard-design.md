# Management Dashboard Design

**Date:** 2026-06-02

## Problem

The existing dashboard is tightly coupled to the FastAPI app — if the app crashes, the dashboard dies with it. There is no visibility into *why* a component is offline, no log trail to investigate failures, and no way to restart individual components or the whole service without SSH access.

## Goals

- Dashboard survives main app crashes — shows offline state + last known error
- Per-component error message + timestamp visible in UI
- Per-component log trail (last 100 entries) accessible in UI
- Restart individual components (detector, health poller) without restarting whole service
- Restart whole service via UI button
- Two-tab layout: OPS (management) + LIVE (operational data, lazy-loaded)

## Out of Scope

- Authentication (local network only)
- Remote access / TLS
- Historical metrics / time-series storage
- Alerting / notifications

---

## Architecture

Two processes, each a systemd service:

| Process | Port | File | Role |
|---|---|---|---|
| Main app | 8000 | `main.py` | People detector, existing |
| Monitor | 8001 | `monitor.py` | Dashboard server, new |

Frontend (browser) talks exclusively to port 8001. Monitor proxies main app data and handles service-level operations. LIVE tab data (WebSocket, camera stream) connects directly to port 8000.

```
Browser
  │
  ├─ port 8001 ──► monitor.py ──► /health, /logs/*, /control/restart/*  ──► main.py (port 8000)
  │                            └─► systemctl restart pi-people-detector
  │
  └─ port 8000 (LIVE tab only) ──► /ws, /stream, /health
```

---

## Main App Additions

### `log_buffer.py` (new file)

Thread-safe in-memory ring buffer, one per component.

```python
COMPONENTS = ("detector", "health", "stream")

# Each buffer holds up to 100 entries:
# {"ts": float, "level": str, "msg": str}
```

API:
- `append(component, level, msg)` — add entry, thread-safe
- `get(component)` → list of dicts, newest last

### `shared_state.py` additions

Eight new fields — per-component last error + timestamp:

| Field | Type | Initial | Set when |
|---|---|---|---|
| `camera_error` | `Optional[str]` | `None` | Camera open/read fails |
| `camera_error_at` | `Optional[float]` | `None` | Same |
| `model_error` | `Optional[str]` | `None` | YOLO model fails to load |
| `model_error_at` | `Optional[float]` | `None` | Same |
| `health_error` | `Optional[str]` | `None` | Health poll throws |
| `health_error_at` | `Optional[float]` | `None` | Same |
| `stream_error` | `Optional[str]` | `None` | MJPEG generator throws |
| `stream_error_at` | `Optional[float]` | `None` | Same |

All eight included in `snapshot()`. Camera and model errors are cleared (set to `None`) when the component recovers.

### `detector.py` changes

- Accepts `stop_event: threading.Event` parameter in `run_detector`
- Both `_run_mock_loop` and `_run_live_loop` check `stop_event.is_set()` at the top of each iteration and return cleanly when set
- Camera exceptions: `log_buffer.append("detector", "ERROR", str(e))`, `state.update(camera_error=str(e), camera_error_at=time.time())`
- Camera recovery (successful read): `state.update(camera_error=None, camera_error_at=None)`
- Model load failure: `log_buffer.append("detector", "ERROR", str(e))`, `state.update(model_error=str(e), model_error_at=time.time())`

### `health.py` changes

- Accepts `stop_event: threading.Event` parameter in `run_health_poller`
- Checks `stop_event.is_set()` each iteration
- On exception: calls `log_buffer.append("health", "ERROR", str(e))` and `state.update(health_error=str(e), health_error_at=time.time())`

### `main.py` changes

- Thread references + stop events at module level:
  ```python
  _detector_stop = threading.Event()
  _health_stop = threading.Event()
  ```
- Both threads started with their stop events in `lifespan`
- New endpoints:
  - `POST /control/restart/detector` — sets `_detector_stop`, starts fresh detector thread with new event
  - `POST /control/restart/health` — sets `_health_stop`, starts fresh health thread with new event
  - `GET /logs/{component}` — returns `log_buffer.get(component)` as JSON
- Stream errors written to `log_buffer.append("stream", ...)` in `_mjpeg_generator` except/finally

---

## `monitor.py` (new file)

Minimal FastAPI app on port 8001. Serves dashboard and proxies main app data.

### State

`MonitorState` dataclass (module-level singleton):
```python
@dataclass
class MonitorState:
    last_health: dict          # last successful /health snapshot
    app_online: bool           # False when /health unreachable
    app_offline_since: Optional[float]  # unix ts when app went offline
    last_poll_at: Optional[float]       # unix ts of last poll attempt
```

### Background polling

`asyncio` background task, runs every 2s:
- `GET http://localhost:8000/health` with 1s timeout
- On success: update `last_health`, set `app_online=True`
- On any exception (connection refused, timeout): set `app_online=False`, set `app_offline_since` if not already set

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve `monitor_static/index.html` |
| `GET` | `/api/status` | `last_health` + `app_online` + `app_offline_since` + `last_poll_at` |
| `GET` | `/api/logs/{component}` | Proxy to `:8000/logs/{component}`; return `[]` if app offline |
| `POST` | `/api/restart/detector` | Proxy to `:8000/control/restart/detector` |
| `POST` | `/api/restart/health` | Proxy to `:8000/control/restart/health` |
| `POST` | `/api/restart/service` | `subprocess.run(["sudo", "systemctl", "restart", "pi-people-detector"])` |

### Static files

`monitor_static/index.html` — self-contained HTML/CSS/JS, no build step.

---

## Dashboard UI

### Layout

```
┌─────────────────────────────────────┐
│  PI MONITOR          [OPS] [LIVE]   │
├─────────────────────────────────────┤
│  (tab content)                      │
└─────────────────────────────────────┘
```

Active tab highlighted. Tab switch immediately stops/starts data loading.

### OPS tab (default)

**Service banner:**
```
pi-people-detector   ● Active    [Restart Service]
```
Status pulled from `app_online` + `last_health`. Button calls `POST /api/restart/service`.

**Component grid** — one row per component (Camera, YOLO, Health Poller):
```
● Camera     online                                    [Restart]
● YOLO       online                                    [Restart]
● Health     offline  "psutil error: ..."  3 mins ago  [Restart]
```
- Green dot = ok, amber = no data yet, red = error field non-null or `app_online=false`
- Error message truncated to 60 chars; click to expand full message
- Timestamp: relative ("3 mins ago") derived from `*_error_at` field
- Restart buttons call `/api/restart/detector` or `/api/restart/health`

**Log viewer:**
```
Component: [Camera ▼]          [Refresh]
─────────────────────────────────────
14:32:01 ERROR  Frame read failed
14:32:03 INFO   Camera recovered
```
- Dropdown: Camera, YOLO+Detector, Health Poller
- Calls `GET /api/logs/{component}` on tab open and on Refresh
- Entries in chronological order, newest at bottom

### LIVE tab

Only activates on tab focus:
- Connects WebSocket to `ws://{location.hostname}:8000/ws`
- Starts polling `http://{location.hostname}:8000/health` every 3s

Disconnects + stops polling on tab leave.

Content mirrors existing `static/index.html` (people count, health stats, camera preview toggle) but sourced from port 8000 directly.

---

## `install.sh` changes

Add after existing service installation:

```bash
echo "[3b/4] Installing monitor service..."
sudo tee "/etc/systemd/system/pi-monitor.service" > /dev/null <<EOF
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

sudo systemctl daemon-reload
sudo systemctl enable --now pi-monitor
```

---

## File Map

| File | Action |
|---|---|
| `log_buffer.py` | Create |
| `monitor.py` | Create |
| `monitor_static/index.html` | Create |
| `shared_state.py` | Modify — 6 new error fields |
| `detector.py` | Modify — stop_event, error tracking, log writes |
| `health.py` | Modify — stop_event, error tracking, log writes |
| `main.py` | Modify — stop events, restart endpoints, /logs endpoint |
| `install.sh` | Modify — add pi-monitor.service |
| `tests/test_shared_state.py` | Modify — new field assertions |
| `tests/test_integration.py` | Modify — new endpoint tests |
| `tests/test_log_buffer.py` | Create |
| `tests/test_monitor.py` | Create |
