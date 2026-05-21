from __future__ import annotations

from rawvision.output.schema import BoundingBox, ElementRole, ElementSource, UIElement


def test_deduplicator_merges_same_element_and_preserves_best_attributes():
    from rawvision.fusion import deduplicator

    uia = UIElement(
        name="Save",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        bbox=BoundingBox(10, 20, 80, 30),
        automation_id="saveButton",
        is_clickable=True,
    )
    cdp = UIElement(
        name="Save changes",
        role=ElementRole.BUTTON,
        source=ElementSource.CDP,
        bbox=BoundingBox(11, 21, 78, 28),
        cdp_node_id=123,
        is_focusable=True,
    )

    merged = deduplicator.deduplicate([cdp, uia])

    assert len(merged) == 1
    element = merged[0]
    assert element.name == "Save"
    assert element.role is ElementRole.BUTTON
    assert element.source is ElementSource.UIA
    assert element.sources == (ElementSource.UIA, ElementSource.CDP)
    assert element.automation_id == "saveButton"
    assert element.cdp_node_id == 123
    assert element.is_clickable is True
    assert element.is_focusable is True


def test_deduplicator_lets_uia_name_win_over_ocr_text_overlap():
    from rawvision.fusion import deduplicator

    uia = UIElement(
        name="Submit",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        bbox=BoundingBox(100, 100, 60, 24),
    )
    ocr = UIElement(
        name="5ubmit",
        role=ElementRole.TEXT,
        source=ElementSource.OCR,
        bbox=BoundingBox(101, 101, 58, 22),
    )

    merged = deduplicator.deduplicate([ocr, uia])

    assert len(merged) == 1
    assert merged[0].name == "Submit"
    assert merged[0].role is ElementRole.BUTTON
    assert merged[0].sources == (ElementSource.UIA, ElementSource.OCR)


def test_deduplicator_keeps_distinct_elements():
    from rawvision.fusion import deduplicator

    first = UIElement(
        name="Save",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        bbox=BoundingBox(10, 10, 50, 20),
    )
    second = UIElement(
        name="Cancel",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        bbox=BoundingBox(200, 10, 50, 20),
    )

    merged = deduplicator.deduplicate([first, second])

    assert len(merged) == 2
    assert [element.name for element in merged] == ["Save", "Cancel"]
