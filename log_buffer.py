import threading
import time
from collections import deque
from typing import Any, Dict, List

COMPONENTS = ("detector", "health", "stream")

_buffers: Dict[str, deque] = {c: deque(maxlen=100) for c in COMPONENTS}
_lock = threading.Lock()


def append(component: str, level: str, msg: str) -> None:
    with _lock:
        _buffers[component].append({"ts": time.time(), "level": level, "msg": msg})


def get(component: str) -> List[Dict[str, Any]]:
    with _lock:
        return list(_buffers[component])
