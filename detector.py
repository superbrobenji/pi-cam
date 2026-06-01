import os
import time
import cv2
import numpy as np
from shared_state import SharedState

_MOCK_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
_CONFIDENCE_THRESHOLD = 0.5
_PERSON_CLASS_ID = 0


def _encode_jpeg(frame: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()


def run_detector(state: SharedState) -> None:
    if os.environ.get("MOCK_CAMERA") == "1":
        state.update(model_ok=True)
        _run_mock_loop(state)
    else:
        _run_live_loop(state)


def _run_mock_loop(state: SharedState) -> None:
    while True:
        t0 = time.monotonic()
        state.update(
            frame=_encode_jpeg(_MOCK_FRAME),
            camera_ok=True,
            count=0,
        )
        time.sleep(max(0.0, 1.0 - (time.monotonic() - t0)))


def _run_live_loop(state: SharedState) -> None:
    from ultralytics import YOLO

    try:
        model = YOLO("yolov8n.pt")
        state.update(model_ok=True)
    except Exception:
        state.update(model_ok=False)
        return

    cap = None
    while True:
        t0 = time.monotonic()
        try:
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)

            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Frame read failed")

            state.update(frame=_encode_jpeg(frame), camera_ok=True)

            results = model(frame, verbose=False)[0]
            count = sum(
                1
                for box in results.boxes
                if int(box.cls[0]) == _PERSON_CLASS_ID
                and float(box.conf[0]) >= _CONFIDENCE_THRESHOLD
            )
            state.update(count=count)

        except Exception:
            state.update(camera_ok=False, count=0)
            if cap is not None:
                cap.release()
                cap = None
            time.sleep(2.0)
            continue

        time.sleep(max(0.0, 1.0 - (time.monotonic() - t0)))
