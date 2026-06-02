import time
from typing import Optional
import psutil
from shared_state import SharedState


def _read_cpu_temp() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return None


def run_health_poller(state: SharedState, interval: float = 2.0) -> None:
    while True:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        state.update(
            cpu_percent=float(cpu),
            ram_used=mem.used,
            ram_total=mem.total,
            cpu_temp=_read_cpu_temp(),
            disk_used=disk.used,
            disk_total=disk.total,
        )
        time.sleep(interval)
