import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from shared_state import SharedState
from detector import run_detector
from health import run_health_poller

state = SharedState()
ws_clients: set[WebSocket] = set()
_ws_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=run_detector, args=(state,), daemon=True).start()
    threading.Thread(target=run_health_poller, args=(state,), daemon=True).start()
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
        while True:
            await websocket.send_json({"count": state.count})
            await asyncio.sleep(1.0)
    except Exception:
        pass
    finally:
        async with _ws_lock:
            ws_clients.discard(websocket)
            state.update(ws_clients=len(ws_clients))


async def _mjpeg_generator():
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        frame = state.get_frame()
        if frame is None:
            return
        if frame:
            yield boundary + frame + b"\r\n"
        await asyncio.sleep(0.1)


@app.get("/stream")
async def stream() -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
