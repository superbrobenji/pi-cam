import pytest
import main as _main_module
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_stream_lock():
    """Ensure _stream_lock is free before and after each test."""
    yield
    lock = _main_module._stream_lock
    if hasattr(lock, "locked") and hasattr(lock, "release") and lock.locked():
        try:
            lock.release()
        except RuntimeError:
            pass


@pytest.fixture()
def _finite_stream(monkeypatch):
    """Replace _mjpeg_generator with a finite version that accepts a request arg."""
    _FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

    async def _finite(request):
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        for _ in range(3):
            yield boundary + _FAKE_JPEG + b"\r\n"

    monkeypatch.setattr(_main_module, "_mjpeg_generator", _finite)


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_expected_keys(client):
    data = client.get("/health").json()
    expected = {
        "count", "camera_ok", "model_ok", "ws_clients",
        "cpu_percent", "ram_used", "ram_total",
        "stream_active", "cpu_temp", "disk_used", "disk_total",
    }
    assert expected.issubset(data.keys())


def test_health_value_types(client):
    data = client.get("/health").json()
    assert isinstance(data["count"], int)
    assert isinstance(data["camera_ok"], bool)
    assert isinstance(data["model_ok"], bool)
    assert isinstance(data["ws_clients"], int)
    assert isinstance(data["cpu_percent"], float)
    assert isinstance(data["ram_used"], int)
    assert isinstance(data["ram_total"], int)
    assert isinstance(data["stream_active"], bool)
    assert data["cpu_temp"] is None or isinstance(data["cpu_temp"], float)
    assert isinstance(data["disk_used"], int)
    assert isinstance(data["disk_total"], int)


def test_websocket_emits_count(client):
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "rawCount" in data
        assert "enteredFrame" in data
        assert "firstSeen" in data
        assert "uniqueTotal" in data
        assert isinstance(data["rawCount"], int)
        assert isinstance(data["enteredFrame"], int)
        assert isinstance(data["firstSeen"], int)
        assert isinstance(data["uniqueTotal"], int)


def test_websocket_increments_ws_clients(client):
    before = client.get("/health").json()["ws_clients"]
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # wait for first message to guarantee ws_clients is updated
        during = client.get("/health").json()["ws_clients"]
    assert during >= before + 1


def test_stream_content_type(client, _finite_stream):
    with client.stream("GET", "/stream") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers["content-type"]


def test_stream_rejects_second_viewer(monkeypatch):
    class _HeldLock:
        def locked(self):
            return True

        def release(self):
            pass

    monkeypatch.setattr(_main_module, "_stream_lock", _HeldLock())
    with TestClient(app) as c:
        response = c.get("/stream")
    assert response.status_code == 409


def test_health_returns_error_fields(client):
    data = client.get("/health").json()
    for field in ("camera_error", "camera_error_at", "model_error", "model_error_at",
                  "health_error", "health_error_at", "stream_error", "stream_error_at"):
        assert field in data, f"Missing field: {field}"
        assert data[field] is None


def test_logs_returns_list_for_known_component(client):
    resp = client.get("/logs/detector")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_logs_returns_404_for_unknown_component(client):
    resp = client.get("/logs/unknown")
    assert resp.status_code == 404


def test_restart_detector_returns_restarting(client):
    resp = client.post("/control/restart/detector")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"


def test_restart_health_returns_restarting(client):
    resp = client.post("/control/restart/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"


def test_reset_tracking_returns_ok(client):
    resp = client.post("/control/reset-tracking")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_settings_returns_ok(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 0.70,
        "iou_threshold": 0.55,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "restarted" in resp.json()


def test_settings_rejects_invalid_model(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8x.pt",
        "confidence_threshold": 0.65,
        "iou_threshold": 0.60,
    })
    assert resp.status_code == 422


def test_settings_rejects_invalid_threshold(client):
    resp = client.post("/control/settings", json={
        "model_name": "yolov8s.pt",
        "confidence_threshold": 1.5,
        "iou_threshold": 0.60,
    })
    assert resp.status_code == 422
