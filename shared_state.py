import threading
from typing import Optional

_FIELDS = frozenset({
    "count", "frame", "camera_ok", "model_ok",
    "ws_clients", "cpu_percent", "ram_used", "ram_total",
    "stream_active", "cpu_temp", "disk_used", "disk_total",
    "camera_error", "camera_error_at",
    "model_error", "model_error_at",
    "health_error", "health_error_at",
    "stream_error", "stream_error_at",
    "entered_frame", "first_seen", "unique_total", "reset_tracking",
    "model_name", "confidence_threshold", "iou_threshold", "inference_tick",
    "track_memory_minutes", "track_high_thresh", "track_low_thresh",
    "new_track_thresh", "match_thresh",
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
        self.cpu_temp: Optional[float] = None
        self.disk_used = 0
        self.disk_total = 0
        self.camera_error: Optional[str] = None
        self.camera_error_at: Optional[float] = None
        self.model_error: Optional[str] = None
        self.model_error_at: Optional[float] = None
        self.health_error: Optional[str] = None
        self.health_error_at: Optional[float] = None
        self.stream_error: Optional[str] = None
        self.stream_error_at: Optional[float] = None
        self.entered_frame = 0
        self.first_seen = 0
        self.unique_total = 0
        self.reset_tracking = False
        self.model_name = "yolov8s.pt"
        self.confidence_threshold = 0.65
        self.iou_threshold = 0.60
        self.inference_tick = 0
        self.track_memory_minutes = 240
        self.track_high_thresh = 0.5
        self.track_low_thresh = 0.1
        self.new_track_thresh = 0.5
        self.match_thresh = 0.8

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
                "camera_error": self.camera_error,
                "camera_error_at": self.camera_error_at,
                "model_error": self.model_error,
                "model_error_at": self.model_error_at,
                "health_error": self.health_error,
                "health_error_at": self.health_error_at,
                "stream_error": self.stream_error,
                "stream_error_at": self.stream_error_at,
                "entered_frame": self.entered_frame,
                "first_seen": self.first_seen,
                "unique_total": self.unique_total,
                "reset_tracking": self.reset_tracking,
                "model_name": self.model_name,
                "confidence_threshold": self.confidence_threshold,
                "iou_threshold": self.iou_threshold,
                "inference_tick": self.inference_tick,
                "track_memory_minutes": self.track_memory_minutes,
                "track_high_thresh": self.track_high_thresh,
                "track_low_thresh": self.track_low_thresh,
                "new_track_thresh": self.new_track_thresh,
                "match_thresh": self.match_thresh,
            }

    def get_frame(self) -> bytes:
        with self._lock:
            return self.frame
