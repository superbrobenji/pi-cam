import threading
import log_buffer


def test_get_empty_initially():
    log_buffer._buffers["detector"].clear()
    assert log_buffer.get("detector") == []


def test_append_and_get():
    log_buffer._buffers["detector"].clear()
    log_buffer.append("detector", "ERROR", "camera failed")
    entries = log_buffer.get("detector")
    assert len(entries) == 1
    assert entries[0]["level"] == "ERROR"
    assert entries[0]["msg"] == "camera failed"
    assert isinstance(entries[0]["ts"], float)


def test_get_returns_copy():
    log_buffer._buffers["detector"].clear()
    log_buffer.append("detector", "INFO", "test")
    result = log_buffer.get("detector")
    result.clear()
    assert len(log_buffer.get("detector")) == 1


def test_max_100_entries():
    log_buffer._buffers["health"].clear()
    for i in range(110):
        log_buffer.append("health", "INFO", f"msg {i}")
    assert len(log_buffer.get("health")) == 100


def test_thread_safe_concurrent_appends():
    log_buffer._buffers["stream"].clear()
    errors = []

    def writer():
        for _ in range(50):
            try:
                log_buffer.append("stream", "INFO", "msg")
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(log_buffer.get("stream")) <= 100
