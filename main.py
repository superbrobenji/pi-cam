import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from shared_state import SharedState
from detector import run_detector
from health import run_health_poller

state = SharedState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=run_detector, args=(state,), daemon=True).start()
    threading.Thread(target=run_health_poller, args=(state,), daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(state.snapshot())
