import os
import time
import threading
import cv2
import numpy as np
from typing import Optional
import log_buffer
from shared_state import SharedState

_MOCK_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
_CONFIDENCE_THRESHOLD = 0.5
_PERSON_CLASS_ID = 0


def _encode_jpeg(frame: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def run_detector(state: SharedState, stop_event: Optional[threading.Event] = None) -> None:
    if stop_event is None:
        stop_event = threading.Event()
    if os.environ.get("MOCK_CAMERA") == "1":
        state.update(model_ok=True)
        _run_mock_loop(state, stop_event)
    else:
        _run_live_loop(state, stop_event)


def _run_mock_loop(state: SharedState, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        t0 = time.monotonic()
        if state.stream_active:
            state.update(frame=_encode_jpeg(_MOCK_FRAME))
        state.update(
            camera_ok=True, count=0,
            entered_frame=0, first_seen=0, unique_total=0,
        )
        stop_event.wait(max(0.0, 1.0 - (time.monotonic() - t0)))


def _run_live_loop(state: SharedState, stop_event: threading.Event) -> None:
    from ultralytics import YOLO

    try:
        model = YOLO("yolov8n.pt")
        state.update(model_ok=True, model_error=None, model_error_at=None)
    except Exception as e:
        msg = str(e)
        log_buffer.append("detector", "ERROR", f"Model load failed: {msg}")
        state.update(model_ok=False, model_error=msg, model_error_at=time.time())
        return

    cap = None
    retry_delay = 2.0
    prev_ids: set = set()
    all_seen_ids: set = set()

    while not stop_event.is_set():
        t0 = time.monotonic()

        if state.reset_tracking:
            prev_ids.clear()
            all_seen_ids.clear()
            state.update(
                reset_tracking=False,
                unique_total=0,
                first_seen=0,
                entered_frame=0,
            )

        try:
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)

            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Frame read failed")

            retry_delay = 2.0
            state.update(camera_ok=True, camera_error=None, camera_error_at=None)

            if state.stream_active:
                state.update(frame=_encode_jpeg(frame))

            results = model.track(frame, persist=True, verbose=False)[0]

            person_indices = [
                i for i, box in enumerate(results.boxes)
                if int(box.cls[0]) == _PERSON_CLASS_ID
                and float(box.conf[0]) >= _CONFIDENCE_THRESHOLD
            ]

            if results.boxes.id is not None:
                track_ids = results.boxes.id.int().cpu().flatten().tolist()
                ids = set(track_ids[i] for i in person_indices)
            else:
                ids = set()

            entered_frame = len(ids - prev_ids)
            new_ids = ids - all_seen_ids
            all_seen_ids.update(ids)
            prev_ids = ids

            del results
            state.update(
                count=len(person_indices),
                entered_frame=entered_frame,
                first_seen=len(new_ids),
                unique_total=len(all_seen_ids),
            )

        except Exception as e:
            msg = str(e)
            log_buffer.append("detector", "ERROR", msg)
            state.update(
                camera_ok=False, count=0,
                camera_error=msg, camera_error_at=time.time(),
            )
            if cap is not None:
                cap.release()
                cap = None
            stop_event.wait(retry_delay)
            retry_delay = min(retry_delay * 2, 30.0)
            continue

        stop_event.wait(max(0.0, 1.0 - (time.monotonic() - t0)))
