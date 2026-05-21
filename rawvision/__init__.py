"""
RawVision - OS-level screen reading for local AI agents.
Reads semantic data from Windows OS instead of pixels.
Works with any LLM including local models.
"""

from __future__ import annotations

from contextlib import contextmanager

__version__ = "1.0.0"

from rawvision.core import RawVision
from rawvision.output.schema import (
    AppType,
    BoundingBox,
    CaptureLayer,
    ElementRole,
    ElementSource,
    LayerResult,
    Point,
    SCHEMA_VERSION,
    ScreenContext,
    ScreenDiff,
    UIElement,
)


def capture(**kwargs) -> ScreenContext:
    """Capture the current screen through the public RawVision API."""
    return RawVision().capture(**kwargs)


@contextmanager
def session():
    """Create a RawVision multi-capture session."""
    with RawVision.session() as vision:
        yield vision


__all__ = [
    "RawVision",
    "ScreenContext",
    "ScreenDiff",
    "UIElement",
    "BoundingBox",
    "Point",
    "ElementRole",
    "ElementSource",
    "AppType",
    "CaptureLayer",
    "LayerResult",
    "SCHEMA_VERSION",
    "capture",
    "session",
]
