import asyncio
import threading
from contextlib import asynccontextmanager
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

_VALID_MODELS = {"yolov8n.pt", "yolov8s.pt", "yolov8m.pt"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=run_detector, args=(state, _detector_stop), daemon=True).start()
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
        last_tick = -1
        while True:
            await asyncio.sleep(1.0)
            current_tick = state.inference_tick
            if current_tick != last_tick:
                last_tick = current_tick
                await websocket.send_json({
                    "rawCount": state.count,
                    "enteredFrame": state.entered_frame,
                    "firstSeen": state.first_seen,
                    "uniqueTotal": state.unique_total,
                })
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
            args=(state, _detector_stop),
            daemon=True,
        ).start()
        restarted = True

    return JSONResponse({"status": "ok", "restarted": restarted})


@app.get("/logs/{component}")
async def get_logs(component: str) -> JSONResponse:
    if component not in log_buffer.COMPONENTS:
        return JSONResponse({"error": f"unknown component: {component}"}, status_code=404)
    return JSONResponse(log_buffer.get(component))
