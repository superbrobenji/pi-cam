import time
import threading
import psutil
from typing import Optional
import log_buffer
from shared_state import SharedState


def _read_cpu_temp() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return None


def run_health_poller(
    state: SharedState,
    interval: float = 2.0,
    stop_event: Optional[threading.Event] = None,
) -> None:
    if stop_event is None:
        stop_event = threading.Event()
    while not stop_event.is_set():
        try:
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
                health_error=None,
                health_error_at=None,
            )
        except Exception as e:
            msg = str(e)
            log_buffer.append("health", "ERROR", msg)
            state.update(health_error=msg, health_error_at=time.time())
        stop_event.wait(interval)
