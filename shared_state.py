import threading

_FIELDS = frozenset({
    "count", "frame", "camera_ok", "model_ok",
    "ws_clients", "cpu_percent", "ram_used", "ram_total",
    "stream_active", "cpu_temp", "disk_used", "disk_total",
})


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self.count = 0
        self.frame = b""
        self.camera_ok = False
        self.model_ok = False
        self.ws_clients = 0
        self.cpu_percent = 0.0
        self.ram_used = 0
        self.ram_total = 0
        self.stream_active = False
        self.cpu_temp = None
        self.disk_used = 0
        self.disk_total = 0

    def update(self, **kwargs):
        unknown = kwargs.keys() - _FIELDS
        if unknown:
            raise KeyError(f"Unknown SharedState fields: {unknown}")
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "count": self.count,
                "camera_ok": self.camera_ok,
                "model_ok": self.model_ok,
                "ws_clients": self.ws_clients,
                "cpu_percent": self.cpu_percent,
                "ram_used": self.ram_used,
                "ram_total": self.ram_total,
                "stream_active": self.stream_active,
                "cpu_temp": self.cpu_temp,
                "disk_used": self.disk_used,
                "disk_total": self.disk_total,
            }

    def get_frame(self) -> bytes:
        with self._lock:
            return self.frame
