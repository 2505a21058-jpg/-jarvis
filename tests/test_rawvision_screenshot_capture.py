from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from rawvision.output.schema import CaptureLayer


def test_screenshot_capture_encodes_resized_png():
    from rawvision.capture import screenshot_capture

    image = np.zeros((100, 200, 3), dtype=np.uint8)
    image[:, :, 1] = 128

    result = screenshot_capture.capture(image=image, max_width=50)

    assert result.layer is CaptureLayer.SCREENSHOT
    assert result.success is True
    assert result.elements == ()
    assert result.raw_data["original_size"] == (200, 100)
    assert result.raw_data["size"] == (50, 25)

    payload = base64.b64decode(result.raw_data["screenshot_b64"])
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    decoded = Image.open(io.BytesIO(payload))
    assert decoded.size == (50, 25)


def test_screenshot_capture_fails_gracefully_without_frame(monkeypatch):
    from rawvision.capture import screenshot_capture

    monkeypatch.setattr(screenshot_capture, "_capture_frame", lambda monitor=None: None)

    result = screenshot_capture.capture()

    assert result.layer is CaptureLayer.SCREENSHOT
    assert result.success is False
    assert "No screenshot" in result.error
    assert result.raw_data["screenshot_b64"] == ""
