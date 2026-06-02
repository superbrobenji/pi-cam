import time
import threading
from shared_state import SharedState
from health import run_health_poller


def test_health_poller_updates_cpu_and_ram():
    state = SharedState()
    t = threading.Thread(target=run_health_poller, args=(state, 0.05), daemon=True)
    t.start()
    time.sleep(0.25)
    snap = state.snapshot()
    assert isinstance(snap["cpu_percent"], float)
    assert snap["ram_used"] > 0
    assert snap["ram_total"] > 0
    assert snap["ram_used"] <= snap["ram_total"]
    assert snap["disk_total"] > 0
    assert snap["disk_used"] >= 0
    assert snap["disk_used"] <= snap["disk_total"]
    assert snap["cpu_temp"] is None or isinstance(snap["cpu_temp"], float)


def test_health_poller_stops_when_stop_event_set():
    state = SharedState()
    stop = threading.Event()
    t = threading.Thread(target=run_health_poller, args=(state, 0.05, stop), daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2.0)
    assert not t.is_alive(), "Health poller should have exited after stop_event set"


def test_health_poller_tracks_error_on_exception(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: (_ for _ in ()).throw(RuntimeError("psutil error")))
    state = SharedState()
    stop = threading.Event()
    t = threading.Thread(target=run_health_poller, args=(state, 0.05, stop), daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2.0)
    snap = state.snapshot()
    assert snap["health_error"] == "psutil error"
    assert snap["health_error_at"] is not None
