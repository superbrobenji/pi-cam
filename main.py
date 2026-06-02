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
