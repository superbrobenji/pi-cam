import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_expected_keys(client):
    data = client.get("/health").json()
    expected = {"count", "camera_ok", "model_ok", "ws_clients", "cpu_percent", "ram_used", "ram_total"}
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
