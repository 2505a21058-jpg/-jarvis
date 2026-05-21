from __future__ import annotations

import numpy as np

from rawvision.output.schema import BoundingBox, CaptureLayer


def test_pixel_diff_reports_regions_after_first_frame(monkeypatch):
    from rawvision.capture import pixel_diff

    pixel_diff.reset_state()

    first = np.zeros((10, 12, 3), dtype=np.uint8)
    second = first.copy()
    third = first.copy()
    third[3:6, 2:6] = 255
    frames = [first, second, third]

    monkeypatch.setattr(pixel_diff, "_capture_frame", lambda monitor=None: frames.pop(0))

    first_result = pixel_diff.capture()
    assert first_result.layer is CaptureLayer.PIXEL_DIFF
    assert first_result.success is True
    assert first_result.raw_data["changed_regions"] == ()

    same_result = pixel_diff.capture()
    assert same_result.success is True
    assert same_result.raw_data["changed_regions"] == ()

    changed_result = pixel_diff.capture()
    regions = changed_result.raw_data["changed_regions"]

    assert changed_result.success is True
    assert len(regions) == 1
    assert isinstance(regions[0], BoundingBox)
    assert regions[0] == BoundingBox(x=2, y=3, width=4, height=3)


def test_pixel_diff_returns_failed_result_when_frame_capture_fails(monkeypatch):
    from rawvision.capture import pixel_diff

    pixel_diff.reset_state()
    monkeypatch.setattr(pixel_diff, "_capture_frame", lambda monitor=None: None)

    result = pixel_diff.capture()

    assert result.layer is CaptureLayer.PIXEL_DIFF
    assert result.success is False
    assert "No framebuffer" in result.error
    assert result.raw_data["changed_regions"] == ()
