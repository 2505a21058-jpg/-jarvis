from __future__ import annotations

from rawvision.fusion import arbitrator, deduplicator, formatter
from rawvision.output.schema import (
    AppType,
    BoundingBox,
    CaptureLayer,
    ElementRole,
    ElementSource,
    LayerResult,
    UIElement,
)


def test_fusion_scores_deduplicates_and_formats_context():
    uia = UIElement(
        name="Submit",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        bbox=BoundingBox(10, 10, 60, 20),
        is_clickable=True,
    )
    ocr = UIElement(
        name="Submit",
        role=ElementRole.TEXT,
        source=ElementSource.OCR,
        bbox=BoundingBox(10, 10, 60, 20),
    )

    merged = deduplicator.deduplicate([ocr, uia])
    assert len(merged) == 1

    scored = arbitrator.apply_score(merged[0])
    assert scored.cross_validated is True
    assert scored.confidence == 1.0

    context = formatter.format_results(
        [
            LayerResult(layer=CaptureLayer.PROCESS_MONITOR, success=True, app_type=AppType.WIN32, app_name="App"),
            LayerResult(layer=CaptureLayer.UIA, success=True, elements=[uia]),
            LayerResult(layer=CaptureLayer.OCR, success=True, elements=[ocr]),
        ]
    )

    assert context.app_name == "App"
    assert len(context.elements) == 1
    assert context.elements[0].name == "Submit"
