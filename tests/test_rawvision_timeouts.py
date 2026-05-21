from __future__ import annotations

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
