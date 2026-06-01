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
    _start_detector(state)
    frame = state.get_frame()
    assert isinstance(frame, bytes)
    assert len(frame) > 0
