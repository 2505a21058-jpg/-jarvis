from __future__ import annotations

import sys
import types

import numpy as np

from rawvision.output.schema import AppType, BoundingBox, CaptureLayer


def test_capture_layers_return_layer_results_without_required_external_services(monkeypatch):
    from rawvision.capture import cv_capture, dom_capture, pixel_diff, screenshot_capture, uia_capture

    assert uia_capture.capture(app_type=AppType.GAME).layer is CaptureLayer.UIA
    assert dom_capture.capture(app_type=AppType.WIN32).layer is CaptureLayer.CDP

    image = np.zeros((10, 10, 3), dtype=np.uint8)
    screenshot = screenshot_capture.capture(image=image, max_width=5)
    assert screenshot.success is True
    assert screenshot.raw_data["size"] == (5, 5)

    pixel_diff.reset_state()
    monkeypatch.setattr(pixel_diff, "_capture_frame", lambda monitor=None: image)
    first = pixel_diff.capture()
    second = pixel_diff.capture()
    assert first.layer is CaptureLayer.PIXEL_DIFF
    assert second.raw_data["changed_regions"] == ()

    cv = cv_capture.capture(image=image, changed_regions=[])
    assert cv.layer is CaptureLayer.OCR
    assert cv.success is True


def test_pixel_diff_changed_region_contract(monkeypatch):
    from rawvision.capture import pixel_diff

    first = np.zeros((8, 8, 3), dtype=np.uint8)
    second = first.copy()
    second[2:5, 3:7] = 255
    frames = [first, second]

    pixel_diff.reset_state()
    monkeypatch.setattr(pixel_diff, "_capture_frame", lambda monitor=None: frames.pop(0))

    pixel_diff.capture()
    result = pixel_diff.capture()

    assert result.raw_data["changed_regions"] == (BoundingBox(3, 2, 4, 3),)


def test_uia_client_is_created_once_and_reused(monkeypatch):
    from rawvision.capture import uia_capture

    create_calls = []
    fake_uia = object()
    fake_comtypes = types.ModuleType("comtypes")
    fake_client = types.ModuleType("comtypes.client")
    fake_gen = types.ModuleType("comtypes.gen")
    fake_gen.UIAutomationClient = types.SimpleNamespace(IUIAutomation="IUIAutomation")

    def fake_create_object(clsid, interface=None):
        create_calls.append((clsid, interface))
        return fake_uia

    fake_client.CreateObject = fake_create_object
    fake_comtypes.client = fake_client
    fake_comtypes.gen = fake_gen

    monkeypatch.setitem(sys.modules, "comtypes", fake_comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", fake_client)
    monkeypatch.setitem(sys.modules, "comtypes.gen", fake_gen)
    monkeypatch.setattr(uia_capture, "_uia_instance", None, raising=False)

    assert uia_capture._get_uia() is fake_uia
    assert uia_capture._get_uia() is fake_uia
    assert create_calls == [
        ("{ff48dba4-60ef-4201-aa87-54103eef594e}", "IUIAutomation")
    ]
