# Resource Exhaustion Fixes Design

**Date:** 2026-06-02

## Problem

The Raspberry Pi 5 becomes unreachable after running for a while, requiring a hard reboot. Root causes identified in code review:

1. **MJPEG generator zombie leak** — `_mjpeg_generator()` in `main.py` has an unbounded `while True` loop. When a client disconnects from `/stream`, Starlette's `StreamingResponse` does not reliably call `aclose()` on the async generator. Zombie generators keep running at 10 iterations/sec, allocating frame bytes objects indefinitely and consuming CPU.

2. **Wasted CPU on JPEG encoding** — `detector.py` calls `_encode_jpeg()` on every frame regardless of whether anyone is watching the stream. JPEG encoding on a 640×480 frame is non-trivial CPU work for a Pi.

3. **Detector FPS not strictly capped** — `sleep(max(0.0, 1.0 - elapsed))` only limits FPS if inference takes less than 1s. If inference is fast (mocked or lightweight), the loop can run faster than 1 FPS.

4. **YOLO tensor retention** — `results = model(frame)[0]` holds output tensors in memory until GC runs. `del results` is never called, so tensors linger longer than necessary.

5. **VideoCapture retry spin** — on camera failure, `cv2.VideoCapture(0)` is retried every 2s with no backoff. If the camera is in a persistently bad state (driver crash, bad fd), this can spin aggressively.

6. **No temperature or disk visibility** — CPU temperature is a primary cause of Pi unresponsiveness (thermal throttling → hang). Disk full can also cause crashes. Neither is monitored.

## Goals

- Eliminate MJPEG generator zombie leak
- Zero CPU spent on JPEG encoding when stream is not active
- Strictly cap detector at 1 FPS
- Release YOLO output tensors promptly after each inference
- Back off VideoCapture retries exponentially on persistent failure
- Expose CPU temperature and disk usage via `/health`

## Out of Scope

- Dashboard UI changes (Sub-project 2)
- WebSocket frame delivery (rejected in favour of targeted fix)
- Changing MJPEG to a different protocol

---

## Design

### `shared_state.py`

Add four new fields:

| Field | Type | Initial | Description |
|---|---|---|---|
| `stream_active` | `bool` | `False` | True when a client is connected to `/stream` |
| `cpu_temp` | `float \| None` | `None` | CPU temperature in °C; None on non-Pi hardware |
| `disk_used` | `int` | `0` | Bytes used on root filesystem |
| `disk_total` | `int` | `0` | Total bytes on root filesystem |

`snapshot()` includes all four new fields.

### `main.py` — MJPEG stream

Replace `_mjpeg_generator()` with a version that:

1. Accepts a `Request` parameter
2. Sets `state.stream_active = True` at entry
3. Polls `await request.is_disconnected()` each iteration — exits loop on disconnect
4. Sets `state.stream_active = False` in `finally` block (runs on disconnect, exception, or cancellation)

Add a `_stream_lock: asyncio.Lock` at module level. The `/stream` endpoint tries to acquire the lock with `asyncio.wait_for(..., timeout=0)` — returns `409 Conflict` immediately if another client holds it. Releases lock when generator exits. This enforces the 1-concurrent-viewer limit.

```python
_stream_lock = asyncio.Lock()

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
    return StreamingResponse(locked_generator(), media_type="multipart/x-mixed-replace; boundary=frame")
```

### `detector.py` — stability fixes

**Skip JPEG encoding when not streaming:**
```python
if state.stream_active:
    state.update(frame=_encode_jpeg(frame))
```
Only encode when a viewer is connected. `state.frame` remains empty bytes otherwise.

**Hard FPS floor:**
The existing `sleep(max(0.0, 1.0 - elapsed))` is correct — it targets 1 FPS and naturally falls below if inference takes >1s. No change needed here; the real gain comes from skipping JPEG encoding when `stream_active=False`, which removes the only near-zero-cost path that could cause unexpectedly short cycles in mock mode.

**Explicit tensor cleanup:**
After extracting count:
```python
count = sum(...)
del results
state.update(count=count)
```

**VideoCapture exponential backoff:**
Replace fixed `time.sleep(2.0)` retry with:
```python
_retry_delay = 2.0
_retry_max = 30.0

# in exception handler:
time.sleep(_retry_delay)
_retry_delay = min(_retry_delay * 2, _retry_max)

# on successful read, reset:
_retry_delay = 2.0
```

### `health.py` — temperature + disk

Add temperature reading:
```python
def _read_cpu_temp() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return None
```

Add disk usage via `psutil.disk_usage('/')`.

Update `run_health_poller` to include both in each `state.update()` call.

---

## Test Changes

- Update `test_health_value_types` to cover `cpu_temp` (None or float), `disk_used` (int ≥ 0), `disk_total` (int > 0)
- Update `test_health_returns_expected_keys` to include new keys
- Update `SharedState` tests to cover new fields and `stream_active` transitions
- Add test: second `/stream` request returns 409
