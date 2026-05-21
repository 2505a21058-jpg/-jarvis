"""
rawvision/fusion/deduplicator.py
Merges same element seen by multiple capture layers.
UIA data wins over CDP wins over OCR for conflicting attributes.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from rawvision.output.schema import ElementSource, UIElement
from rawvision.utils.spatial import is_same_element, name_similarity

logger = logging.getLogger("rawvision.fusion.deduplicator")

_SOURCE_PRIORITY = {
    ElementSource.UIA: 3,
    ElementSource.CDP: 2,
    ElementSource.OCR: 1,
    ElementSource.SCREENSHOT: 0,
    ElementSource.FUSED: 4,
}


def deduplicate(elements: list[UIElement]) -> list[UIElement]:
    """
    Merge elements that represent the same UI element.
    Returns deduplicated list with fused confidence.
    """
    if not elements:
        return []

    groups: list[list[UIElement]] = []
    assigned = set()

    for i, el in enumerate(elements):
        if i in assigned:
            continue
        group = [el]
        assigned.add(i)
        for j, other in enumerate(elements):
            if j in assigned:
                continue
            if _should_merge(el, other):
                group.append(other)
                assigned.add(j)
        groups.append(group)

    result = []
    for group in groups:
        if len(group) == 1:
            result.append(group[0])
        else:
            result.append(_merge_group(group))
    return result


def _merge_group(group: list[UIElement]) -> UIElement:
    """Merge a group of same-element detections."""
    group_sorted = sorted(
        group,
        key=lambda e: _SOURCE_PRIORITY.get(e.source, 0),
        reverse=True,
    )
    primary = group_sorted[0]

    best_name = primary.name
    best_name_priority = _SOURCE_PRIORITY.get(primary.source, 0)
    for el in group_sorted:
        priority = _SOURCE_PRIORITY.get(el.source, 0)
        if not el.name:
            continue
        if not best_name or priority > best_name_priority:
            best_name = el.name
            best_name_priority = priority
        elif priority == best_name_priority and len(el.name) > len(best_name):
            best_name = el.name

    best_bbox = primary.bbox
    for el in group_sorted:
        if el.bbox and el.bbox.is_valid:
            best_bbox = el.bbox
            break

    avg_conf = sum(e.confidence for e in group) / len(group)
    fused_conf = min(1.0, avg_conf + 0.15)
    sources_list = tuple(dict.fromkeys(e.source.value for e in group_sorted))

    return UIElement(
        name=best_name,
        role=primary.role,
        value=primary.value or next((e.value for e in group_sorted if e.value), ""),
        placeholder=primary.placeholder or next((e.placeholder for e in group_sorted if e.placeholder), ""),
        description=primary.description or next((e.description for e in group_sorted if e.description), ""),
        bbox=best_bbox,
        confidence=fused_conf,
        source=primary.source,
        cross_validated=True,
        sources=sources_list,
        runtime_id=primary.runtime_id or next((e.runtime_id for e in group_sorted if e.runtime_id), None),
        cdp_node_id=primary.cdp_node_id or next((e.cdp_node_id for e in group_sorted if e.cdp_node_id), None),
        hwnd=primary.hwnd or next((e.hwnd for e in group_sorted if e.hwnd), None),
        automation_id=primary.automation_id or next((e.automation_id for e in group_sorted if e.automation_id), None),
        cdp_node_path=primary.cdp_node_path or next((e.cdp_node_path for e in group_sorted if e.cdp_node_path), None),
        is_clickable=any(e.is_clickable for e in group),
        is_typeable=any(e.is_typeable for e in group),
        is_focusable=any(e.is_focusable for e in group),
        is_scrollable=any(e.is_scrollable for e in group),
        is_visible=any(e.is_visible for e in group),
        is_enabled=any(e.is_enabled for e in group),
        is_focused=any(e.is_focused for e in group),
        is_expanded=primary.is_expanded,
        is_selected=primary.is_selected,
        keyboard_shortcut=primary.keyboard_shortcut,
        parent_name=primary.parent_name,
        parent_role=primary.parent_role,
        sibling_index=primary.sibling_index,
        children_count=primary.children_count,
        depth=primary.depth,
        captured_at=primary.captured_at,
    )


def _should_merge(a: UIElement, b: UIElement) -> bool:
    try:
        if is_same_element(a, b):
            return True
    except Exception as exc:
        logger.debug("[DEDUP] Spatial match failed: %s", exc)

    if not (a.bbox and b.bbox):
        return False

    if a.bbox.iou(b.bbox) < 0.45:
        return False

    if not (
        a.source == ElementSource.OCR
        or b.source == ElementSource.OCR
        or a.role == b.role
    ):
        return False

    if a.name and b.name:
        return (
            name_similarity(a.name, b.name) >= 0.6
            or _ocr_text_similarity(a.name, b.name) >= 0.55
        )

    return True


def _ocr_text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
