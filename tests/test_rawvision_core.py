from __future__ import annotations

from rawvision.output.schema import (
    AppType,
    BoundingBox,
    CaptureLayer,
    ElementRole,
    ElementSource,
    LayerResult,
    ScreenContext,
    UIElement,
)


def test_rawvision_capture_orchestrates_layers_and_formats_context(monkeypatch):
    from rawvision import core

    process = LayerResult(
        layer=CaptureLayer.PROCESS_MONITOR,
        success=True,
        app_type=AppType.CHROME,
        app_name="Chrome",
        window_title="Example",
        app_pid=42,
        cdp_port=9222,
        raw_data={"process_info": {"hwnd": 101, "app_friendly_name": "Chrome"}},
    )
    uia_element = UIElement(
        name="Save",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        bbox=BoundingBox(10, 10, 80, 30),
        is_clickable=True,
    )
    ocr_element = UIElement(
        name="5ave",
        role=ElementRole.TEXT,
        source=ElementSource.OCR,
        bbox=BoundingBox(10, 10, 80, 30),
    )

    monkeypatch.setattr(core.process_monitor, "capture", lambda hwnd=None: process)
    monkeypatch.setattr(
        core.uia_capture,
        "capture",
        lambda hwnd=None, app_type=AppType.UNKNOWN: LayerResult(
            layer=CaptureLayer.UIA,
            success=True,
            elements=[uia_element],
        ),
    )
    monkeypatch.setattr(
        core.dom_capture,
        "capture",
        lambda cdp_port=None, app_type=AppType.UNKNOWN, electron_app="": LayerResult(
            layer=CaptureLayer.CDP,
            success=False,
            error="not connected",
        ),
    )
    monkeypatch.setattr(
        core.pixel_diff,
        "capture",
        lambda: LayerResult(
            layer=CaptureLayer.PIXEL_DIFF,
            success=True,
            raw_data={"changed_regions": (BoundingBox(0, 0, 100, 50),)},
        ),
    )
    monkeypatch.setattr(
        core.cv_capture,
        "capture",
        lambda changed_regions=None: LayerResult(
            layer=CaptureLayer.OCR,
            success=True,
            elements=[ocr_element],
        ),
    )
    monkeypatch.setattr(
        core.screenshot_capture,
        "capture",
        lambda: LayerResult(
            layer=CaptureLayer.SCREENSHOT,
            success=True,
            raw_data={"screenshot_b64": "abc"},
        ),
    )

    context = core.RawVision(max_workers=3).capture()

    assert isinstance(context, ScreenContext)
    assert context.app_name == "Chrome"
    assert context.window_title == "Example"
    assert context.screenshot_b64 == "abc"
    assert CaptureLayer.CDP in context.layers_failed
    assert context.find("Save", role=ElementRole.BUTTON) is not None


def test_rawvision_capture_converts_layer_exceptions_to_failures(monkeypatch):
    from rawvision import core

    process = LayerResult(
        layer=CaptureLayer.PROCESS_MONITOR,
        success=True,
        app_type=AppType.WIN32,
        raw_data={"process_info": {"hwnd": 1}},
    )

    monkeypatch.setattr(core.process_monitor, "capture", lambda hwnd=None: process)

    def raise_uia(**_kwargs):
        raise RuntimeError("uia broke")

    monkeypatch.setattr(core.uia_capture, "capture", raise_uia)
    monkeypatch.setattr(core.dom_capture, "capture", lambda **_kwargs: LayerResult(layer=CaptureLayer.CDP, success=False))
    monkeypatch.setattr(core.pixel_diff, "capture", lambda: LayerResult(layer=CaptureLayer.PIXEL_DIFF, success=True))
    monkeypatch.setattr(core.cv_capture, "capture", lambda changed_regions=None: LayerResult(layer=CaptureLayer.OCR, success=True))
    monkeypatch.setattr(core.screenshot_capture, "capture", lambda: LayerResult(layer=CaptureLayer.SCREENSHOT, success=True))

    context = core.RawVision(max_workers=2).capture()

    assert CaptureLayer.UIA in context.layers_failed
    assert isinstance(context, ScreenContext)


def test_rawvision_session_context_manager():
    from rawvision import core

    vision = core.RawVision()

    with vision.session() as session:
        assert session is vision
