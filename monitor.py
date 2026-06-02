import asyncio
import subprocess
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

MAIN_APP_URL = "http://localhost:8000"


@dataclass
class MonitorState:
    last_health: Dict[str, Any] = field(default_factory=dict)
    app_online: bool = False
    app_offline_since: Optional[float] = None
    last_poll_at: Optional[float] = None


_state = MonitorState()


async def _poll_main_app() -> None:
    async with httpx.AsyncClient(timeout=1.0) as client:
        while True:
            try:
                resp = await client.get(f"{MAIN_APP_URL}/health")
                resp.raise_for_status()
                _state.last_health = resp.json()
                _state.app_online = True
                _state.app_offline_since = None
            except Exception:
                if _state.app_online:
                    _state.app_offline_since = time.time()
                _state.app_online = False
            _state.last_poll_at = time.time()
            await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_poll_main_app())
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("monitor_static/index.html")


@app.get("/api/status")
async def status() -> JSONResponse:
    return JSONResponse({
        **_state.last_health,
        "app_online": _state.app_online,
        "app_offline_since": _state.app_offline_since,
        "last_poll_at": _state.last_poll_at,
    })


@app.get("/api/logs/{component}")
async def get_logs(component: str) -> JSONResponse:
    if not _state.app_online:
        return JSONResponse([])
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{MAIN_APP_URL}/logs/{component}")
            return JSONResponse(resp.json())
    except Exception:
        return JSONResponse([])


@app.post("/api/restart/detector")
async def restart_detector() -> JSONResponse:
    if not _state.app_online:
        return JSONResponse({"error": "main app offline"}, status_code=503)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{MAIN_APP_URL}/control/restart/detector")
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/restart/health")
async def restart_health() -> JSONResponse:
    if not _state.app_online:
        return JSONResponse({"error": "main app offline"}, status_code=503)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{MAIN_APP_URL}/control/restart/health")
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/restart/service")
async def restart_service() -> JSONResponse:
    result = subprocess.run(
        ["sudo", "systemctl", "restart", "pi-people-detector"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return JSONResponse({"error": result.stderr}, status_code=500)
    return JSONResponse({"status": "restarting"})
