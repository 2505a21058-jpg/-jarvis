from __future__ import annotations

from rawvision import BoundingBox, ElementRole, ScreenContext, UIElement


def test_public_schema_builds_searchable_context():
    search = UIElement(
        name="Search",
        role=ElementRole.INPUT,
        bbox=BoundingBox(1, 2, 100, 20),
        is_typeable=True,
    )
    context = ScreenContext(app_name="Chrome", app_type="chrome", elements=[search])

    assert context.find("Search", role=ElementRole.INPUT) == search
    assert context.interactive_elements == [search]
    assert "Search" in context.to_llm()
