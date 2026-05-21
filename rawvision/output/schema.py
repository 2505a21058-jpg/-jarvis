"""
rawvision/output/schema.py

Production-grade core data structures for RawVision.

Design:
- Immutable after construction (thread-safe)
- O(1) element lookup via indexes
- Multi-strategy fingerprinting (collision-resistant)
- Accurate token budgeting
- Schema versioning for forward compatibility
- Full validation on construction
- ScreenDiff for change detection between captures

Zero required external dependencies.
tiktoken is used for accurate token counting if available.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Optional

logger = logging.getLogger("rawvision.schema")

SCHEMA_VERSION = "1.0.0"


# -- Token counting ------------------------------------------------------------

def _count_tokens(text: str) -> int:
    """
    Count tokens accurately if tiktoken is available.
    Falls back to a char-based estimate and never raises.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(str(text or "")))
    except Exception:
        text = str(text or "")
        has_unicode = any(ord(char) > 127 for char in text)
        chars_per_token = 2.5 if has_unicode else 4.0
        return max(1, int(len(text) / chars_per_token))


# -- Enums ---------------------------------------------------------------------

class ElementRole(str, Enum):
    BUTTON = "button"
    INPUT = "input"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    LISTITEM = "listitem"
    LINK = "link"
    IMAGE = "image"
    TEXT = "text"
    HEADING = "heading"
    MENU = "menu"
    MENUITEM = "menuitem"
    TOOLBAR = "toolbar"
    DIALOG = "dialog"
    ALERT = "alert"
    TAB = "tab"
    TABPANEL = "tabpanel"
    TREE = "tree"
    TREEITEM = "treeitem"
    TABLE = "table"
    ROW = "row"
    CELL = "cell"
    SCROLLBAR = "scrollbar"
    SLIDER = "slider"
    PROGRESSBAR = "progressbar"
    STATUSBAR = "statusbar"
    WINDOW = "window"
    PANE = "pane"
    GROUP = "group"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class ElementSource(str, Enum):
    UIA = "uia"
    CDP = "cdp"
    OCR = "ocr"
    SCREENSHOT = "screenshot"
    FUSED = "fused"


class AppType(str, Enum):
    CHROME = "chrome"
    ELECTRON = "electron"
    OFFICE = "office"
    WIN32 = "win32"
    UWP = "uwp"
    TERMINAL = "terminal"
    GAME = "game"
    UNKNOWN = "unknown"


class CaptureLayer(str, Enum):
    PROCESS_MONITOR = "process_monitor"
    UIA = "uia"
    CDP = "cdp"
    PIXEL_DIFF = "pixel_diff"
    OCR = "ocr"
    SCREENSHOT = "screenshot"


# -- Geometry ------------------------------------------------------------------

@dataclass(frozen=True)
class Point:
    x: int
    y: int

    def __post_init__(self):
        object.__setattr__(self, "x", _coerce_int(self.x, "Point.x"))
        object.__setattr__(self, "y", _coerce_int(self.y, "Point.y"))

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y}

    def __str__(self) -> str:
        return f"({self.x},{self.y})"


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self):
        object.__setattr__(self, "x", _coerce_int(self.x, "BoundingBox.x"))
        object.__setattr__(self, "y", _coerce_int(self.y, "BoundingBox.y"))
        object.__setattr__(self, "width", _coerce_int(self.width, "BoundingBox.width"))
        object.__setattr__(self, "height", _coerce_int(self.height, "BoundingBox.height"))
        if self.width < 0 or self.height < 0:
            raise ValueError(f"BoundingBox width/height cannot be negative: {self.width}x{self.height}")

    @property
    def center(self) -> Point:
        return Point(self.x + self.width // 2, self.y + self.height // 2)

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0

    @property
    def is_visible_on_screen(self) -> bool:
        return self.x > -self.width and self.y > -self.height and self.x < 7680 and self.y < 4320

    def contains(self, point: Point) -> bool:
        return self.x <= point.x <= self.right and self.y <= point.y <= self.bottom

    def overlaps(self, other: BoundingBox) -> bool:
        return not (
            self.right < other.x
            or other.right < self.x
            or self.bottom < other.y
            or other.bottom < self.y
        )

    def iou(self, other: BoundingBox) -> float:
        """Intersection over Union for deduplication across capture layers."""
        ix = max(0, min(self.right, other.right) - max(self.x, other.x))
        iy = max(0, min(self.bottom, other.bottom) - max(self.y, other.y))
        intersection = ix * iy
        if intersection == 0:
            return 0.0
        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0

    def position_bucket(self, screen_w: int = 600, screen_h: int = 768) -> str:
        """Nine-zone position descriptor for stable fingerprinting."""
        cx = self.center.x / max(screen_w, 1)
        cy = self.center.y / max(screen_h, 1)
        vertical = "top" if cy < 0.33 else ("bot" if cy > 0.66 else "mid")
        horizontal = "left" if cx < 0.33 else ("right" if cx > 0.66 else "center")
        return f"{vertical}-{horizontal}"

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict | None) -> Optional["BoundingBox"]:
        if not data:
            return None
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 0),
            height=data.get("height", 0),
        )

    def __str__(self) -> str:
        return f"[{self.x},{self.y} {self.width}x{self.height}]"


# -- UIElement -----------------------------------------------------------------

@dataclass(frozen=True)
class UIElement:
    """A single immutable UI element on screen."""

    name: str
    role: ElementRole

    value: str = ""
    placeholder: str = ""
    description: str = ""

    bbox: Optional[BoundingBox] = None

    confidence: float = 1.0
    source: ElementSource = ElementSource.UIA
    cross_validated: bool = False
    sources: tuple = field(default_factory=tuple)

    runtime_id: Optional[str] = None
    cdp_node_id: Optional[int] = None
    hwnd: Optional[int] = None
    automation_id: Optional[str] = None
    cdp_node_path: Optional[str] = None

    is_clickable: bool = False
    is_typeable: bool = False
    is_focusable: bool = False
    is_scrollable: bool = False
    is_visible: bool = True
    is_enabled: bool = True
    is_focused: bool = False
    is_expanded: Optional[bool] = None
    is_selected: Optional[bool] = None

    keyboard_shortcut: str = ""
    parent_name: str = ""
    parent_role: str = ""
    sibling_index: int = 0
    children_count: int = 0
    depth: int = 0

    captured_at: float = field(default_factory=time.time)

    def __post_init__(self):
        object.__setattr__(self, "name", str(self.name or ""))
        object.__setattr__(self, "value", str(self.value or ""))
        object.__setattr__(self, "placeholder", str(self.placeholder or ""))
        object.__setattr__(self, "description", str(self.description or ""))
        object.__setattr__(self, "role", _coerce_enum(self.role, ElementRole, ElementRole.UNKNOWN, "role"))
        object.__setattr__(self, "source", _coerce_enum(self.source, ElementSource, ElementSource.UIA, "source"))
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))
        object.__setattr__(self, "bbox", _coerce_bbox(self.bbox))
        object.__setattr__(self, "sources", tuple(
            _coerce_enum(source, ElementSource, ElementSource.UIA, "sources")
            for source in (self.sources or ())
        ))
        object.__setattr__(self, "sibling_index", max(0, _coerce_int(self.sibling_index, "sibling_index")))
        object.__setattr__(self, "children_count", max(0, _coerce_int(self.children_count, "children_count")))
        object.__setattr__(self, "depth", max(0, _coerce_int(self.depth, "depth")))
        object.__setattr__(self, "captured_at", float(self.captured_at))

        if not self.name.strip() and not self.value.strip():
            logger.debug("UIElement created with empty name and value (role=%s)", self.role.value)
        if self.bbox and not self.bbox.is_valid:
            logger.debug("UIElement has zero-size bbox: %s '%s'", self.role.value, self.name)

    @property
    def element_id(self) -> str:
        """Stable multi-strategy semantic fingerprint."""
        if self.automation_id:
            return _sha256_short(f"auto:{self.automation_id}:{self.role.value}", length=16)
        if self.runtime_id and self.hwnd:
            return _sha256_short(f"runtime:{self.hwnd}:{self.runtime_id}:{self.role.value}", length=16)
        if self.cdp_node_path:
            return _sha256_short(f"cdp:{self.cdp_node_path}", length=16)
        if self.cdp_node_id is not None and self.parent_name:
            raw = f"cdp-node:{self.parent_name}:{self.cdp_node_id}:{self.role.value}"
            return _sha256_short(raw, length=16)

        components = [
            self.role.value,
            _normalize_name(self.name or self.value),
            str(self.parent_role or ""),
            _normalize_name(self.parent_name),
            str(self.sibling_index),
            self.bbox.position_bucket() if self.bbox else "nopos",
        ]
        return _sha256_short("|".join(components), length=16)

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.captured_at) > 3.0

    @property
    def center(self) -> Optional[Point]:
        return self.bbox.center if self.bbox else None

    @property
    def is_actionable(self) -> bool:
        return (
            self.is_visible
            and self.is_enabled
            and (self.is_clickable or self.is_typeable or self.is_focusable)
            and self.confidence >= 0.5
        )

    def to_dict(self) -> dict:
        return {
            "element_id": self.element_id,
            "name": self.name,
            "role": self.role.value,
            "value": self.value,
            "placeholder": self.placeholder,
            "description": self.description,
            "confidence": round(self.confidence, 3),
            "source": self.source.value,
            "sources": [source.value for source in self.sources],
            "cross_validated": self.cross_validated,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "is_clickable": self.is_clickable,
            "is_typeable": self.is_typeable,
            "is_focusable": self.is_focusable,
            "is_scrollable": self.is_scrollable,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "is_focused": self.is_focused,
            "is_expanded": self.is_expanded,
            "is_selected": self.is_selected,
            "keyboard_shortcut": self.keyboard_shortcut,
            "runtime_id": self.runtime_id,
            "cdp_node_id": self.cdp_node_id,
            "hwnd": self.hwnd,
            "automation_id": self.automation_id,
            "cdp_node_path": self.cdp_node_path,
            "parent_name": self.parent_name,
            "parent_role": self.parent_role,
            "sibling_index": self.sibling_index,
            "children_count": self.children_count,
            "depth": self.depth,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UIElement":
        payload = dict(data or {})
        payload.pop("element_id", None)
        payload["bbox"] = BoundingBox.from_dict(payload.get("bbox"))
        return cls(**payload)

    def to_llm_str(self) -> str:
        """Compact natural language for LLM injection."""
        parts = [f"{self.role.value}:{self.name!r}"]
        if self.value and self.value != self.name:
            parts.append(f"={self.value!r}")
        if self.placeholder:
            parts.append(f"hint={self.placeholder!r}")
        if self.is_focused:
            parts.append("FOCUSED")
        if not self.is_enabled:
            parts.append("disabled")
        if self.is_selected:
            parts.append("selected")
        if self.keyboard_shortcut:
            parts.append(f"key={self.keyboard_shortcut}")

        actions = []
        if self.is_clickable:
            actions.append("click")
        if self.is_typeable:
            actions.append("type")
        if self.is_scrollable:
            actions.append("scroll")
        if actions:
            parts.append(f"[{','.join(actions)}]")
        return " ".join(parts)

    def __str__(self) -> str:
        return self.to_llm_str()


# -- LayerResult ---------------------------------------------------------------

@dataclass(frozen=True)
class LayerResult:
    """Output from a single capture layer."""

    layer: CaptureLayer
    success: bool
    elements: tuple[UIElement, ...] = field(default_factory=tuple)
    raw_data: dict = field(default_factory=dict)
    error: str = ""
    elapsed_ms: float = 0.0
    confidence: float = 1.0

    app_type: Optional[AppType] = None
    app_name: str = ""
    app_pid: int = 0
    window_title: str = ""
    cdp_port: Optional[int] = None

    def __post_init__(self):
        object.__setattr__(self, "layer", _coerce_enum(self.layer, CaptureLayer, CaptureLayer.SCREENSHOT, "layer"))
        object.__setattr__(self, "elements", tuple(self.elements or ()))
        object.__setattr__(self, "raw_data", MappingProxyType(dict(self.raw_data or {})))
        object.__setattr__(self, "error", str(self.error or ""))
        object.__setattr__(self, "elapsed_ms", max(0.0, float(self.elapsed_ms)))
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))
        if self.app_type is not None:
            object.__setattr__(self, "app_type", _coerce_enum(self.app_type, AppType, AppType.UNKNOWN, "app_type"))
        object.__setattr__(self, "app_name", str(self.app_name or ""))
        object.__setattr__(self, "app_pid", max(0, _coerce_int(self.app_pid, "app_pid")))
        object.__setattr__(self, "window_title", str(self.window_title or ""))


# -- ScreenDiff ----------------------------------------------------------------

@dataclass(frozen=True)
class ScreenDiff:
    """Difference between two ScreenContext captures."""

    appeared: tuple
    disappeared: tuple
    changed: tuple
    unchanged_count: int
    capture_gap_ms: float

    def __post_init__(self):
        object.__setattr__(self, "appeared", tuple(self.appeared or ()))
        object.__setattr__(self, "disappeared", tuple(self.disappeared or ()))
        object.__setattr__(self, "changed", tuple(self.changed or ()))
        object.__setattr__(self, "unchanged_count", max(0, _coerce_int(self.unchanged_count, "unchanged_count")))
        object.__setattr__(self, "capture_gap_ms", float(self.capture_gap_ms))

    @property
    def significant(self) -> bool:
        return bool(self.appeared or self.disappeared or self.changed)

    @property
    def summary(self) -> str:
        parts = []
        if self.appeared:
            parts.append(f"{len(self.appeared)} new: {', '.join(element.name for element in self.appeared[:3])}")
        if self.disappeared:
            parts.append(f"{len(self.disappeared)} gone: {', '.join(element.name for element in self.disappeared[:3])}")
        if self.changed:
            parts.append(f"{len(self.changed)} changed")
        return " | ".join(parts) if parts else "no significant changes"

    def to_llm(self) -> str:
        if not self.significant:
            return "Screen unchanged after action."

        lines = ["Screen changed:"]
        for element in self.appeared[:5]:
            lines.append(f"  + appeared: {element.to_llm_str()}")
        for element in self.disappeared[:5]:
            lines.append(f"  - disappeared: {element.name!r}")
        for before, after in list(self.changed)[:5]:
            if before.value != after.value:
                lines.append(f"  ~ {before.name!r}: {before.value!r} -> {after.value!r}")
            elif before.is_focused != after.is_focused:
                lines.append(f"  ~ {before.name!r}: focus changed")
            elif before.is_enabled != after.is_enabled:
                lines.append(f"  ~ {before.name!r}: enabled changed")
        return "\n".join(lines)


# -- ScreenContext -------------------------------------------------------------

@dataclass(frozen=True)
class ScreenContext:
    """Unified immutable output of RawVision with O(1) lookup indexes."""

    schema_version: str = SCHEMA_VERSION

    app_name: str = ""
    app_type: AppType = AppType.UNKNOWN
    window_title: str = ""
    app_pid: int = 0

    cdp_port: Optional[int] = None
    cdp_url: str = ""

    elements: tuple[UIElement, ...] = field(default_factory=tuple)

    captured_at: float = field(default_factory=time.time)
    capture_ms: float = 0.0
    layers_used: tuple[CaptureLayer, ...] = field(default_factory=tuple)
    layers_failed: tuple[CaptureLayer, ...] = field(default_factory=tuple)

    screenshot_b64: Optional[str] = None
    screenshot_path: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "schema_version", str(self.schema_version or SCHEMA_VERSION))
        object.__setattr__(self, "app_name", str(self.app_name or ""))
        object.__setattr__(self, "app_type", _coerce_enum(self.app_type, AppType, AppType.UNKNOWN, "app_type"))
        object.__setattr__(self, "window_title", str(self.window_title or ""))
        object.__setattr__(self, "app_pid", max(0, _coerce_int(self.app_pid, "app_pid")))
        object.__setattr__(self, "cdp_url", str(self.cdp_url or ""))
        object.__setattr__(self, "elements", tuple(
            element if isinstance(element, UIElement) else UIElement.from_dict(element)
            for element in (self.elements or ())
        ))
        object.__setattr__(self, "captured_at", float(self.captured_at))
        object.__setattr__(self, "capture_ms", max(0.0, float(self.capture_ms)))
        object.__setattr__(self, "layers_used", tuple(
            _coerce_enum(layer, CaptureLayer, CaptureLayer.SCREENSHOT, "layers_used")
            for layer in (self.layers_used or ())
        ))
        object.__setattr__(self, "layers_failed", tuple(
            _coerce_enum(layer, CaptureLayer, CaptureLayer.SCREENSHOT, "layers_failed")
            for layer in (self.layers_failed or ())
        ))

        by_id: dict[str, UIElement] = {}
        by_role: dict[ElementRole, list[UIElement]] = {}
        by_name: dict[str, list[UIElement]] = {}

        for element in self.elements:
            element_id = element.element_id
            if element_id in by_id:
                logger.debug("Fingerprint collision: '%s' and '%s' share id %s", by_id[element_id].name, element.name, element_id)
            by_id[element_id] = element
            by_role.setdefault(element.role, []).append(element)
            name_key = element.name.lower().strip()
            if name_key:
                by_name.setdefault(name_key, []).append(element)

        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_by_role", MappingProxyType({role: tuple(items) for role, items in by_role.items()}))
        object.__setattr__(self, "_by_name", MappingProxyType({name: tuple(items) for name, items in by_name.items()}))

    @property
    def interactive_elements(self) -> list[UIElement]:
        return [element for element in self.elements if element.is_actionable]

    @property
    def high_confidence_elements(self) -> list[UIElement]:
        return [element for element in self.elements if element.confidence >= 0.8]

    @property
    def summary(self) -> str:
        interactive = self.interactive_elements
        focused = self.find_focused()
        parts = [f"App:{self.app_name}"]
        if self.window_title:
            parts.append(f"{self.window_title!r}")
        if self.cdp_url:
            domain = self.cdp_url.split("/")[2] if "//" in self.cdp_url else self.cdp_url
            parts.append(f"url:{domain}")
        parts.append(f"{len(self.elements)}el")
        parts.append(f"{len(interactive)}interactive")
        if focused:
            parts.append(f"focused:{focused.name!r}")
        return " | ".join(parts)

    def find(
        self,
        name: str = "",
        role: Optional[ElementRole] = None,
        min_confidence: float = 0.5,
        actionable_only: bool = False,
    ) -> Optional[UIElement]:
        """O(1) for exact name or role index, O(k) for filtered candidates."""
        name_lower = str(name or "").lower().strip()
        normalized_role = _coerce_optional_enum(role, ElementRole, "role")

        if name_lower:
            candidates = self._by_name.get(name_lower, ())
            for element in candidates:
                if normalized_role and element.role is not normalized_role:
                    continue
                if element.confidence < min_confidence:
                    continue
                if actionable_only and not element.is_actionable:
                    continue
                return element

        pool = self._by_role.get(normalized_role, ()) if normalized_role else self.elements
        for element in pool:
            if element.confidence < min_confidence:
                continue
            if actionable_only and not element.is_actionable:
                continue
            if name_lower and name_lower not in element.name.lower():
                continue
            return element
        return None

    def find_all(
        self,
        name: str = "",
        role: Optional[ElementRole] = None,
        min_confidence: float = 0.5,
        actionable_only: bool = False,
    ) -> list[UIElement]:
        name_lower = str(name or "").lower().strip()
        normalized_role = _coerce_optional_enum(role, ElementRole, "role")
        pool = self._by_role.get(normalized_role, ()) if normalized_role else self.elements
        results = []
        for element in pool:
            if element.confidence < min_confidence:
                continue
            if actionable_only and not element.is_actionable:
                continue
            if name_lower and name_lower not in element.name.lower():
                continue
            results.append(element)
        return results

    def find_by_id(self, element_id: str) -> Optional[UIElement]:
        return self._by_id.get(str(element_id or ""))

    def find_focused(self) -> Optional[UIElement]:
        return next((element for element in self.elements if element.is_focused), None)

    def diff(self, other: "ScreenContext") -> ScreenDiff:
        self_ids = {element.element_id: element for element in self.elements}
        other_ids = {element.element_id: element for element in other.elements}

        appeared = tuple(element for element_id, element in other_ids.items() if element_id not in self_ids)
        disappeared = tuple(element for element_id, element in self_ids.items() if element_id not in other_ids)
        changed = []
        for element_id, before in self_ids.items():
            if element_id not in other_ids:
                continue
            after = other_ids[element_id]
            if (
                before.value != after.value
                or before.is_focused != after.is_focused
                or before.is_enabled != after.is_enabled
            ):
                changed.append((before, after))

        return ScreenDiff(
            appeared=appeared,
            disappeared=disappeared,
            changed=tuple(changed),
            unchanged_count=max(0, len(self_ids) - len(changed) - len(disappeared)),
            capture_gap_ms=(other.captured_at - self.captured_at) * 1000,
        )

    def to_llm(self, max_tokens: int = 800) -> str:
        """Natural language for any LLM, sorted by action relevance."""
        lines = []
        context = f"App: {self.app_name}"
        if self.window_title:
            context += f" | Window: {self.window_title!r}"
        if self.cdp_url:
            context += f" | URL: {self.cdp_url}"
        lines.append(context)
        lines.append("Elements:")

        tokens_used = _count_tokens("\n".join(lines))
        shown = 0
        visible_elements = [element for element in sorted(self.elements, key=_llm_sort_key) if element.is_visible]

        for element in visible_elements:
            line = f"  - {element.to_llm_str()}"
            line_tokens = _count_tokens(line)
            if tokens_used + line_tokens > max_tokens:
                remaining = len(visible_elements) - shown
                if remaining > 0:
                    lines.append(f"  ... +{remaining} more elements")
                break
            lines.append(line)
            tokens_used += line_tokens
            shown += 1
        return "\n".join(lines)

    def to_gemma(self, max_tokens: int = 300) -> str:
        """Ultra-compact context for small local models."""
        lines = [f"Screen:{self.app_name}"]
        if self.cdp_url:
            domain = self.cdp_url.split("/")[2] if "//" in self.cdp_url else self.cdp_url
            lines.append(f"URL:{domain}")

        interactive = sorted(self.interactive_elements, key=_gemma_sort_key)[:12]
        if interactive:
            lines.append("UI:")
            tokens = _count_tokens("\n".join(lines))
            for element in interactive:
                line = f" {element.role.value[0]}:{element.name!r}"
                if element.value:
                    line += f"={element.value!r}"
                if element.is_focused:
                    line += "*"
                line_tokens = _count_tokens(line)
                if tokens + line_tokens > max_tokens:
                    break
                lines.append(line)
                tokens += line_tokens
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "app_name": self.app_name,
            "app_type": self.app_type.value,
            "window_title": self.window_title,
            "app_pid": self.app_pid,
            "cdp_port": self.cdp_port,
            "cdp_url": self.cdp_url,
            "summary": self.summary,
            "captured_at": self.captured_at,
            "capture_ms": round(self.capture_ms, 1),
            "layers_used": [layer.value for layer in self.layers_used],
            "layers_failed": [layer.value for layer in self.layers_failed],
            "screenshot_b64": self.screenshot_b64,
            "screenshot_path": self.screenshot_path,
            "element_count": len(self.elements),
            "elements": [element.to_dict() for element in self.elements],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_openai_vision(self) -> list[dict]:
        content = [{"type": "text", "text": self.to_llm(max_tokens=1000)}]
        if self.screenshot_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{self.screenshot_b64}", "detail": "low"},
            })
        return [{"role": "user", "content": content}]

    def to_anthropic(self) -> list[dict]:
        content = [{"type": "text", "text": self.to_llm(max_tokens=1000)}]
        if self.screenshot_b64:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": self.screenshot_b64},
            })
        return [{"role": "user", "content": content}]

    @classmethod
    def empty(cls, app_name: str = "", app_type: AppType = AppType.UNKNOWN) -> "ScreenContext":
        return cls(app_name=app_name, app_type=app_type, elements=tuple())

    @classmethod
    def from_dict(cls, data: dict) -> "ScreenContext":
        migrated = migrate_schema(data)
        payload = dict(migrated)
        payload.pop("summary", None)
        payload.pop("element_count", None)
        payload["elements"] = [UIElement.from_dict(element) for element in payload.get("elements", [])]
        return cls(**payload)

    def __str__(self) -> str:
        return self.summary

    def __len__(self) -> int:
        return len(self.elements)


# -- Schema migration ----------------------------------------------------------

def migrate_schema(data: dict) -> dict:
    """Migrate older serialized ScreenContext dicts to SCHEMA_VERSION."""
    if not isinstance(data, dict):
        raise TypeError("ScreenContext migration expects a dict")

    migrated = dict(data)
    version = str(migrated.get("schema_version") or "0.0.0")
    if version == SCHEMA_VERSION:
        return migrated

    if "app" in migrated and "app_name" not in migrated:
        migrated["app_name"] = migrated.pop("app")
    if "title" in migrated and "window_title" not in migrated:
        migrated["window_title"] = migrated.pop("title")

    migrated.setdefault("elements", [])
    migrated.setdefault("layers_used", [])
    migrated.setdefault("layers_failed", [])
    migrated["schema_version"] = SCHEMA_VERSION
    logger.debug("Migrated ScreenContext schema %s -> %s", version, SCHEMA_VERSION)
    return migrated


# -- Helpers -------------------------------------------------------------------

def _sha256_short(raw: str, length: int = 16) -> str:
    """SHA256 truncated to length chars."""
    return hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:length]


def _normalize_name(name: str) -> str:
    """Normalize element name for fingerprinting."""
    if not name:
        return ""
    normalized = str(name).lower().strip()
    normalized = re.sub(r"\b\d{3,}\b", "#", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:60]


def _coerce_int(value: Any, field_name: str) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer, got {value!r}") from exc


def _coerce_enum(value: Any, enum_cls: type[Enum], default: Enum, field_name: str) -> Enum:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    try:
        return enum_cls(str(value).lower())
    except ValueError as exc:
        valid = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"{field_name} must be one of: {valid}") from exc


def _coerce_optional_enum(value: Any, enum_cls: type[Enum], field_name: str) -> Optional[Enum]:
    if value is None:
        return None
    return _coerce_enum(value, enum_cls, None, field_name)


def _coerce_bbox(value: Any) -> Optional[BoundingBox]:
    if value is None or isinstance(value, BoundingBox):
        return value
    if isinstance(value, dict):
        return BoundingBox.from_dict(value)
    raise ValueError(f"bbox must be BoundingBox, dict, or None; got {type(value).__name__}")


def _llm_sort_key(element: UIElement) -> float:
    score = element.confidence
    if element.is_focused:
        score += 10.0
    if element.role in (ElementRole.DIALOG, ElementRole.ALERT, ElementRole.HEADING, ElementRole.WINDOW):
        score += 2.0
    if element.is_actionable:
        score += 1.5
    if element.cross_validated:
        score += 0.5
    if not element.is_enabled:
        score -= 2.0
    if not element.is_visible:
        score -= 5.0
    return -score


def _gemma_sort_key(element: UIElement) -> float:
    return (-10.0 if element.is_focused else 0.0) - element.confidence


__all__ = [
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
    "migrate_schema",
]
