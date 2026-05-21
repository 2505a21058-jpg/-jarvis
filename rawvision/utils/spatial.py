"""
rawvision/utils/spatial.py

Spatial utilities for UI element analysis.

Used by:
- Deduplicator: find overlapping elements from different layers
- Formatter: sort elements by visual hierarchy
- Hands: calculate click targets
"""

from __future__ import annotations

import math
from typing import Optional

from rawvision.output.schema import BoundingBox, Point, UIElement


# -- Distance and overlap ------------------------------------------------------

def distance(p1: Point, p2: Point) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


def center_distance(a: BoundingBox, b: BoundingBox) -> float:
    """Distance between centers of two bounding boxes."""
    return distance(a.center, b.center)


def iou(a: BoundingBox, b: BoundingBox) -> float:
    """
    Intersection over Union.
    1.0 = identical boxes.
    0.0 = no overlap.
    Used to detect same element seen by multiple layers.
    """
    return a.iou(b)


def is_same_element(
    a: UIElement,
    b: UIElement,
    iou_threshold: float = 0.5,
    name_similarity_threshold: float = 0.6,
) -> bool:
    """
    Determine if two UIElements from different layers
    represent the same real UI element.

    Used by deduplicator/arbitrator.
    """
    if a.role != b.role:
        return False

    if a.bbox and b.bbox:
        overlap = iou(a.bbox, b.bbox)
        if overlap >= iou_threshold:
            return True
        if overlap >= 0.2:
            sim = name_similarity(a.name, b.name)
            return sim >= name_similarity_threshold

    if a.name and b.name:
        return name_similarity(a.name, b.name) >= 0.8

    return False


def name_similarity(a: str, b: str) -> float:
    """
    Simple name similarity score 0.0-1.0.
    Uses token overlap -- no NLP dependency.
    """
    if not a or not b:
        return 0.0
    if a.lower() == b.lower():
        return 1.0

    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# -- Visual hierarchy ----------------------------------------------------------

def reading_order_key(
    el: UIElement,
    screen_w: int = 1366,
    screen_h: int = 768,
) -> tuple:
    """
    Sort key for reading order (top-to-bottom, left-to-right).
    Used by formatter to order elements naturally.
    """
    if not el.bbox:
        return (999, 999)

    row = el.bbox.y // 20
    col = el.bbox.x

    return (row, col)


def visual_importance_score(el: UIElement) -> float:
    """
    Score element by visual importance.
    Higher = show first in LLM context.

    Factors:
    - Focused element: highest priority
    - Dialogs/alerts: very high (need attention)
    - Headings: high (provide context)
    - Interactive enabled: medium-high
    - Text labels: medium
    - Disabled/invisible: low
    """
    score = el.confidence

    if el.is_focused:
        score += 10.0
    if el.role.value in ("dialog", "alert"):
        score += 3.0
    if el.role.value == "heading":
        score += 2.0
    if el.is_actionable:
        score += 1.5
    if el.cross_validated:
        score += 0.5
    if not el.is_enabled:
        score -= 2.0
    if not el.is_visible:
        score -= 5.0

    return score


# -- Clustering ----------------------------------------------------------------

def cluster_by_proximity(
    elements: list[UIElement],
    max_distance: int = 50,
) -> list[list[UIElement]]:
    """
    Group elements that are spatially close together.
    Used to detect form groups, toolbars, nav menus.
    Returns list of clusters (each cluster = list of elements).
    """
    if not elements:
        return []

    with_bbox = [element for element in elements if element.bbox]
    without_bbox = [element for element in elements if not element.bbox]

    clusters: list[list[UIElement]] = []
    assigned = set()

    for i, el in enumerate(with_bbox):
        if i in assigned:
            continue
        cluster = [el]
        assigned.add(i)

        for j, other in enumerate(with_bbox):
            if j in assigned:
                continue
            if center_distance(el.bbox, other.bbox) <= max_distance:
                cluster.append(other)
                assigned.add(j)

        clusters.append(cluster)

    for el in without_bbox:
        clusters.append([el])

    return clusters


def find_nearest(
    target: BoundingBox,
    elements: list[UIElement],
    role_filter: Optional[str] = None,
) -> Optional[UIElement]:
    """
    Find element nearest to a given bounding box.
    Useful for finding labels near input fields.
    """
    candidates = elements
    if role_filter:
        candidates = [
            element for element in elements
            if element.role.value == role_filter
        ]

    if not candidates:
        return None

    return min(
        (element for element in candidates if element.bbox),
        key=lambda element: center_distance(target, element.bbox),
        default=None,
    )


# -- DPI correction ------------------------------------------------------------

def get_dpi_scale() -> float:
    """
    Get Windows DPI scaling factor.
    Critical for correct click coordinates on
    high-DPI displays and laptops with scaling.
    Returns 1.0 on non-Windows or if detection fails.
    """
    try:
        import ctypes

        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


def dpi_correct(point: Point) -> Point:
    """
    Correct coordinates for DPI scaling.
    Use before any SendInput coordinate-based click.
    """
    scale = get_dpi_scale()
    if scale == 1.0:
        return point
    return Point(
        int(point.x / scale),
        int(point.y / scale),
    )


def screen_to_logical(bbox: BoundingBox) -> BoundingBox:
    """
    Convert physical screen coordinates to logical coordinates.
    Required for SendInput on scaled displays.
    """
    scale = get_dpi_scale()
    if scale == 1.0:
        return bbox
    return BoundingBox(
        x=int(bbox.x / scale),
        y=int(bbox.y / scale),
        width=int(bbox.width / scale),
        height=int(bbox.height / scale),
    )
