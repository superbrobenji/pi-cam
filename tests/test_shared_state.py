import threading
from shared_state import SharedState


def test_initial_values():
    state = SharedState()
    snap = state.snapshot()
    assert snap["count"] == 0
    assert snap["camera_ok"] is False
    assert snap["model_ok"] is False
    assert snap["ws_clients"] == 0
    assert snap["cpu_percent"] == 0.0
    assert snap["ram_used"] == 0
    assert snap["ram_total"] == 0


def test_update_and_snapshot():
    state = SharedState()
    state.update(count=3, camera_ok=True)
    snap = state.snapshot()
    assert snap["count"] == 3
    assert snap["camera_ok"] is True


def test_update_does_not_leak_frame_into_snapshot():
    state = SharedState()
    state.update(frame=b"testdata")
    snap = state.snapshot()
    assert "frame" not in snap


def test_get_frame_returns_bytes():
    state = SharedState()
    state.update(frame=b"testdata")
    assert state.get_frame() == b"testdata"


def test_thread_safe_concurrent_updates():
    state = SharedState()
    errors = []

    def writer(val):
        for _ in range(200):
            try:
                state.update(count=val)
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert isinstance(state.snapshot()["count"], int)


def test_update_rejects_unknown_fields():
    import pytest
    state = SharedState()
    with pytest.raises(KeyError):
        state.update(cpu_percentt=50.0)
