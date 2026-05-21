from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from rawvision.output.schema import (
    AppType,
    BoundingBox,
    CaptureLayer,
    ElementRole,
    ElementSource,
    Point,
    SCHEMA_VERSION,
    ScreenContext,
    UIElement,
)


def test_bounding_box_geometry_and_validation():
    bbox = BoundingBox(100, 50, 200, 40)

    assert bbox.center == Point(200, 70)
    assert bbox.position_bucket() == "top-center"
    assert bbox.iou(BoundingBox(150, 60, 100, 30)) > 0
    assert bbox.iou(BoundingBox(1000, 1000, 10, 10)) == 0.0

    with pytest.raises(ValueError):
        BoundingBox(0, 0, -1, 10)


def test_ui_element_validates_enums_clamps_confidence_and_fingerprints():
    bbox = BoundingBox(100, 50, 200, 40)
    first = UIElement(
        name="Search",
        role="input",
        bbox=bbox,
        is_typeable=True,
        is_focusable=True,
        confidence=1.5,
        source="cdp",
        automation_id="SearchBox",
    )
    second = UIElement(
        name="Different visible label",
        role=ElementRole.INPUT,
        bbox=BoundingBox(500, 50, 200, 40),
        automation_id="SearchBox",
    )

    assert first.role is ElementRole.INPUT
    assert first.source is ElementSource.CDP
    assert first.confidence == 1.0
    assert first.element_id == second.element_id
    assert first.is_actionable
    assert "input" in first.to_llm_str()


def test_screen_context_is_immutable_and_has_o1_indexes():
    search = UIElement(name="Search", role=ElementRole.INPUT, is_typeable=True, is_focusable=True)
    submit = UIElement(name="Submit", role=ElementRole.BUTTON, is_clickable=True, is_focused=True)
    ctx = ScreenContext(
        app_name="Chrome",
        app_type="chrome",
        layers_used=["uia", "cdp"],
        elements=[search, submit],
    )

    assert ctx.app_type is AppType.CHROME
    assert ctx.layers_used == (CaptureLayer.UIA, CaptureLayer.CDP)
    assert ctx.find("Search") == search
    assert ctx.find("Search", role=ElementRole.INPUT) == search
    assert ctx.find_by_id(search.element_id) == search
    assert ctx.find_focused() == submit
    assert len(ctx.interactive_elements) == 2

    with pytest.raises(FrozenInstanceError):
        ctx.elements = tuple()


def test_screen_context_to_llm_prioritizes_focused_and_actionable_elements():
    search = UIElement(name="Search", role=ElementRole.INPUT, is_typeable=True, is_focusable=True)
    submit = UIElement(name="Submit", role=ElementRole.BUTTON, is_clickable=True, is_focused=True)
    label = UIElement(name="Legal footer", role=ElementRole.TEXT, confidence=0.99)
    ctx = ScreenContext(app_name="Chrome", elements=[label, search, submit])

    llm = ctx.to_llm(max_tokens=200)

    assert llm.index("Submit") < llm.index("Search")
    assert "Legal footer" in llm


def test_screen_diff_detects_appeared_disappeared_and_changed():
    before_input = UIElement(name="Search", role=ElementRole.INPUT, value="", is_typeable=True)
    after_input = UIElement(name="Search", role=ElementRole.INPUT, value="trains", is_typeable=True)
    button = UIElement(name="Submit", role=ElementRole.BUTTON, is_clickable=True)
    before = ScreenContext(app_name="Chrome", elements=[before_input, button], captured_at=10.0)
    after = ScreenContext(app_name="Chrome", elements=[after_input], captured_at=10.5)

    diff = before.diff(after)

    assert diff.significant
    assert diff.disappeared == (button,)
    assert diff.changed == ((before_input, after_input),)
    assert diff.capture_gap_ms == 500
    assert "changed" in diff.summary


def test_screen_context_migrates_old_schema_dicts():
    data = {
        "schema_version": "0.9.0",
        "app_name": "Chrome",
        "app_type": "chrome",
        "elements": [
            {
                "name": "Search",
                "role": "input",
                "source": "cdp",
                "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
                "is_typeable": True,
            }
        ],
    }

    ctx = ScreenContext.from_dict(data)

    assert ctx.schema_version == SCHEMA_VERSION
    assert ctx.find("Search", role=ElementRole.INPUT).bbox == BoundingBox(1, 2, 3, 4)
