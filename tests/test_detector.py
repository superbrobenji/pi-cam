import time
import threading
from shared_state import SharedState
from detector import run_detector


def _start_detector(state: SharedState) -> None:
    threading.Thread(target=run_detector, args=(state,), daemon=True).start()
    time.sleep(0.3)


def test_mock_sets_camera_ok():
    state = SharedState()
    _start_detector(state)
    assert state.camera_ok is True


def test_mock_sets_model_ok():
    state = SharedState()
    _start_detector(state)
    assert state.model_ok is True


def test_mock_count_is_int():
    state = SharedState()
    _start_detector(state)
    assert isinstance(state.count, int)


def test_mock_frame_is_nonempty_bytes():
    state = SharedState()
    state.update(stream_active=True)
    _start_detector(state)
    frame = state.get_frame()
    assert isinstance(frame, bytes)
    assert len(frame) > 0


def test_mock_frame_empty_when_stream_inactive():
    state = SharedState()
    # stream_active defaults to False — no frame should be encoded
    _start_detector(state)
    assert state.get_frame() == b""


def test_mock_frame_nonempty_when_stream_active():
    state = SharedState()
    state.update(stream_active=True)
    _start_detector(state)
    frame = state.get_frame()
    assert isinstance(frame, bytes)
    assert len(frame) > 0


def test_detector_stops_when_stop_event_set():
    state = SharedState()
    stop = threading.Event()
    t = threading.Thread(target=run_detector, args=(state, stop), daemon=True)
    t.start()
    time.sleep(0.4)
    stop.set()
    t.join(timeout=3.0)
    assert not t.is_alive(), "Detector thread should have exited after stop_event set"
