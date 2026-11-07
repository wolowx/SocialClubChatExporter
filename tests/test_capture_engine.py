import os
import queue
import socket

import pytest

from socialclub_exporter.capture_engine import CaptureEngine


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(
    os.environ.get("SOCIALCLUB_EXPORTER_RUN_INTEGRATION") != "1",
    reason="set SOCIALCLUB_EXPORTER_RUN_INTEGRATION=1 to run",
)
@pytest.mark.integration
def test_capture_engine_starts_and_stops(tmp_path):
    engine = CaptureEngine(free_port(), tmp_path, queue.Queue())
    engine.start()
    try:
        assert engine.running is True
    finally:
        engine.stop()
    assert engine.running is False


@pytest.mark.skipif(
    os.environ.get("SOCIALCLUB_EXPORTER_RUN_INTEGRATION") != "1",
    reason="set SOCIALCLUB_EXPORTER_RUN_INTEGRATION=1 to run",
)
@pytest.mark.integration
def test_capture_engine_start_raises_when_port_in_use(tmp_path):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        port = blocker.getsockname()[1]
        engine = CaptureEngine(port, tmp_path, queue.Queue())
        with pytest.raises(RuntimeError):
            engine.start()
        engine.stop()
    finally:
        blocker.close()
