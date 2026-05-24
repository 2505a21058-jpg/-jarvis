from __future__ import annotations

import threading
import time

from rawvision.utils import timeout


def test_capture_layer_timeouts_allow_first_run_initialization():
    assert timeout._LAYER_TIMEOUTS == {
        "process_monitor": 5.0,
        "uia": 8.0,
        "cdp": 6.0,
        "pixel_diff": 4.0,
        "ocr": 8.0,
        "screenshot": 5.0,
    }


def test_run_with_timeout_requests_cooperative_cancellation():
    exited = threading.Event()

    def cooperative_work(cancel_event):
        try:
            while not cancel_event.is_set():
                time.sleep(0.005)
        finally:
            exited.set()

    result = timeout.run_with_timeout(
        cooperative_work,
        timeout=0.01,
        default="cancelled",
        layer_name="cooperative",
    )

    assert result == "cancelled"
    assert exited.wait(0.2)
