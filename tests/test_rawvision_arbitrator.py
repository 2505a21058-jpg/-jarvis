from __future__ import annotations

from rawvision.output.schema import BoundingBox, ElementRole, ElementSource, UIElement


def test_arbitrator_scores_by_source_and_cross_validation():
    from rawvision.fusion import arbitrator

    uia = UIElement(name="Save", role=ElementRole.BUTTON, source=ElementSource.UIA)
    ocr = UIElement(name="Save", role=ElementRole.TEXT, source=ElementSource.OCR)
    cdp_cross = UIElement(
        name="Save",
        role=ElementRole.BUTTON,
        source=ElementSource.CDP,
        sources=(ElementSource.CDP, ElementSource.OCR),
    )

    assert arbitrator.score_element(uia) == 0.95
    assert arbitrator.score_element(ocr) == 0.71
    assert arbitrator.score_element(cdp_cross) == 1.0

    scored = arbitrator.apply_score(cdp_cross)
    assert scored.confidence == 1.0
    assert scored.cross_validated is True


def test_arbitrator_penalizes_stale_offscreen_and_disabled_elements():
    from rawvision.fusion import arbitrator

    element = UIElement(
        name="Submit",
        role=ElementRole.BUTTON,
        source=ElementSource.CDP,
        bbox=BoundingBox(x=8000, y=20, width=40, height=20),
        is_enabled=False,
        captured_at=100.0,
    )

    score = arbitrator.score_element(element, now=104.0)

    assert score == 0.33


def test_arbitrator_scores_many_elements_without_mutating_originals():
    from rawvision.fusion import arbitrator

    original = UIElement(
        name="Read me",
        role=ElementRole.TEXT,
        source=ElementSource.SCREENSHOT,
        confidence=0.99,
    )

    scored = arbitrator.score_elements([original])[0]

    assert original.confidence == 0.99
    assert scored.confidence == 0.45
    assert scored.source is ElementSource.SCREENSHOT
