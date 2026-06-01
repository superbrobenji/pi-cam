import time
import psutil
from shared_state import SharedState


def run_health_poller(state: SharedState, interval: float = 2.0) -> None:
    while True:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        state.update(
            cpu_percent=float(cpu),
            ram_used=mem.used,
            ram_total=mem.total,
        )
        time.sleep(interval)
