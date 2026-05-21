"""
rawvision/fusion/arbitrator.py
Confidence scoring per element from each layer.
"""

from __future__ import annotations

from dataclasses import replace
import logging
import time
from typing import Optional

from rawvision.output.schema import ElementSource, UIElement
from rawvision.utils.spatial import is_same_element

logger = logging.getLogger("rawvision.fusion.arbitrator")

_BASE_CONFIDENCE = {
    ElementSource.UIA: 0.95,
    ElementSource.CDP: 0.93,
    ElementSource.OCR: 0.71,
    ElementSource.SCREENSHOT: 0.45,
    ElementSource.FUSED: 1.00,
}

_CROSS_VALIDATION_BONUS = 0.15
_FOCUS_BONUS = 0.05
_STALE_PENALTY = 0.20
_DISABLED_PENALTY = 0.10
_OFFSCREEN_PENALTY = 0.50
_BBOX_OFFSCREEN_PENALTY = 0.30


def score_element(
    el: UIElement,
    all_elements: Optional[list[UIElement]] = None,
    now: Optional[float] = None,
) -> float:
    """Compute final confidence score for an element."""
    base = _BASE_CONFIDENCE.get(el.source, 0.5)
    score = min(base, max(0.0, float(el.confidence)))

    if _is_cross_validated(el, all_elements or []):
        score = min(1.0, score + _CROSS_VALIDATION_BONUS)

    if el.is_focused:
        score = min(1.0, score + _FOCUS_BONUS)
    if _is_stale(el, now=now):
        score = max(0.0, score - _STALE_PENALTY)
    if not el.is_enabled:
        score = max(0.0, score - _DISABLED_PENALTY)
    if not el.is_visible:
        score = max(0.0, score - _OFFSCREEN_PENALTY)
    elif el.bbox and not el.bbox.is_visible_on_screen:
        score = max(0.0, score - _BBOX_OFFSCREEN_PENALTY)

    return round(score, 3)


def score_all(elements: list[UIElement]) -> list[UIElement]:
    """Re-score all elements considering cross-validation."""
    result = []
    for el in elements:
        cross = _is_cross_validated(el, elements)
        new_score = score_element(el, elements)
        result.append(
            UIElement(
                name=el.name,
                role=el.role,
                value=el.value,
                placeholder=el.placeholder,
                description=el.description,
                bbox=el.bbox,
                confidence=new_score,
                source=el.source,
                cross_validated=cross,
                sources=el.sources,
                runtime_id=el.runtime_id,
                cdp_node_id=el.cdp_node_id,
                hwnd=el.hwnd,
                automation_id=el.automation_id,
                cdp_node_path=el.cdp_node_path,
                is_clickable=el.is_clickable,
                is_typeable=el.is_typeable,
                is_focusable=el.is_focusable,
                is_scrollable=el.is_scrollable,
                is_visible=el.is_visible,
                is_enabled=el.is_enabled,
                is_focused=el.is_focused,
                is_expanded=el.is_expanded,
                is_selected=el.is_selected,
                keyboard_shortcut=el.keyboard_shortcut,
                parent_name=el.parent_name,
                parent_role=el.parent_role,
                sibling_index=el.sibling_index,
                children_count=el.children_count,
                depth=el.depth,
                captured_at=el.captured_at,
            )
        )
    return result


def apply_score(
    element: UIElement,
    all_elements: Optional[list[UIElement]] = None,
    now: Optional[float] = None,
) -> UIElement:
    """Compatibility wrapper: return a copy of one element with its score."""
    cross = _is_cross_validated(element, all_elements or [])
    score = score_element(element, all_elements=all_elements, now=now)
    return replace(element, confidence=score, cross_validated=cross)


def score_elements(
    elements: list[UIElement] | tuple[UIElement, ...],
    now: Optional[float] = None,
) -> tuple[UIElement, ...]:
    """Compatibility wrapper for older callers."""
    element_list = list(elements or [])
    return tuple(
        apply_score(element, all_elements=element_list, now=now)
        for element in element_list
    )


def _is_cross_validated(
    el: UIElement,
    all_elements: list[UIElement],
) -> bool:
    if len(set(el.sources or ())) >= 2:
        return True

    for other in all_elements:
        if other is el or other.source == el.source:
            continue
        try:
            if is_same_element(el, other):
                return True
        except Exception as exc:
            logger.debug("[ARBITRATOR] Cross-validation check failed: %s", exc)
    return False


def _is_stale(el: UIElement, now: Optional[float]) -> bool:
    if now is None:
        return el.is_stale
    return (now - float(el.captured_at)) > 3.0
