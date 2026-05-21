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


def test_formatter_builds_screen_context_from_layer_results():
    from rawvision.fusion import formatter

    process = LayerResult(
        layer=CaptureLayer.PROCESS_MONITOR,
        success=True,
        app_type=AppType.CHROME,
        app_name="Chrome",
        app_pid=42,
        window_title="Example",
        cdp_port=9222,
    )
    uia = UIElement(
        name="Save",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        bbox=BoundingBox(10, 10, 80, 30),
        is_clickable=True,
    )
    ocr = UIElement(
        name="5ave",
        role=ElementRole.TEXT,
        source=ElementSource.OCR,
        bbox=BoundingBox(11, 11, 78, 28),
    )
    screenshot = LayerResult(
        layer=CaptureLayer.SCREENSHOT,
        success=True,
        raw_data={"screenshot_b64": "abc123"},
    )

    context = formatter.format_results(
        [
            process,
            LayerResult(layer=CaptureLayer.UIA, success=True, elements=[uia]),
            LayerResult(layer=CaptureLayer.OCR, success=True, elements=[ocr]),
            screenshot,
        ],
        max_tokens=200,
    )

    assert isinstance(context, ScreenContext)
    assert context.app_name == "Chrome"
    assert context.app_type is AppType.CHROME
    assert context.app_pid == 42
    assert context.window_title == "Example"
    assert context.cdp_port == 9222
    assert context.screenshot_b64 == "abc123"
    assert context.layers_used == (
        CaptureLayer.PROCESS_MONITOR,
        CaptureLayer.UIA,
        CaptureLayer.OCR,
        CaptureLayer.SCREENSHOT,
    )
    assert context.layers_failed == ()
    assert len(context.elements) == 1
    assert context.elements[0].name == "Save"
    assert context.elements[0].cross_validated is True
    assert context.elements[0].confidence == 1.0


def test_formatter_tracks_failed_layers_and_enforces_token_budget():
    from rawvision.fusion import formatter

    focused = UIElement(
        name="Focused",
        role=ElementRole.INPUT,
        source=ElementSource.CDP,
        is_focused=True,
        is_typeable=True,
    )
    many = [
        UIElement(
            name=f"Long label number {idx} with extra words",
            role=ElementRole.TEXT,
            source=ElementSource.OCR,
        )
        for idx in range(30)
    ]
    failed = LayerResult(
        layer=CaptureLayer.CDP,
        success=False,
        error="no browser",
    )

    context = formatter.format_results(
        [
            failed,
            LayerResult(layer=CaptureLayer.OCR, success=True, elements=[focused, *many]),
        ],
        max_tokens=45,
    )

    assert context.layers_failed == (CaptureLayer.CDP,)
    assert context.elements[0].name == "Focused"
    assert len(context.elements) < 31


def test_formatter_orders_layer_status_deterministically():
    from rawvision.fusion import formatter

    context = formatter.format_results(
        [
            LayerResult(layer=CaptureLayer.SCREENSHOT, success=True),
            LayerResult(layer=CaptureLayer.CDP, success=False),
            LayerResult(layer=CaptureLayer.PROCESS_MONITOR, success=True),
            LayerResult(layer=CaptureLayer.UIA, success=True),
        ]
    )

    assert context.layers_used == (
        CaptureLayer.PROCESS_MONITOR,
        CaptureLayer.UIA,
        CaptureLayer.SCREENSHOT,
    )
    assert context.layers_failed == (CaptureLayer.CDP,)
