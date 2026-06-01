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
