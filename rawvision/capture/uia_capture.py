"""
rawvision/capture/uia_capture.py

Layer 1 -- Windows UI Automation.
Reads the semantic element tree directly from Windows.

Works on:
  Native Win32 apps: full support
  WPF/WinForms:      full support
  Office apps:       full support
  UWP apps:          full support
  Electron apps:     partial (shell only, not content)
  Chrome browser:    partial (address bar, toolbar only)
  Games:             none

Speed: ~15ms for simple apps, ~80ms for complex apps.
Timeout: 8 seconds hard limit.

Output: list[UIElement] with source=ElementSource.UIA
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from rawvision.output.schema import (
    AppType,
    BoundingBox,
    CaptureLayer,
    ElementRole,
    ElementSource,
    LayerResult,
    UIElement,
)
from rawvision.utils.timeout import run_with_timeout

logger = logging.getLogger("rawvision.capture.uia")

_MAX_ELEMENTS = 200
_MAX_DEPTH = 8
_MIN_ELEMENT_SIZE = 4
_uia_instance = None

# UIA control type to ElementRole mapping
_UIA_ROLE_MAP = {
    0x0000: ElementRole.UNKNOWN,
    0xC350: ElementRole.BUTTON,      # UIA_ButtonControlTypeId
    0xC352: ElementRole.CHECKBOX,    # UIA_CheckBoxControlTypeId
    0xC353: ElementRole.DROPDOWN,    # UIA_ComboBoxControlTypeId
    0xC354: ElementRole.UNKNOWN,     # Custom
    0xC355: ElementRole.UNKNOWN,     # DataGrid
    0xC356: ElementRole.CELL,        # DataItem
    0xC357: ElementRole.DOCUMENT,    # Document
    0xC358: ElementRole.UNKNOWN,     # Edit -> mapped below
    0xC359: ElementRole.GROUP,       # Group
    0xC35A: ElementRole.UNKNOWN,     # Header
    0xC35B: ElementRole.UNKNOWN,     # HeaderItem
    0xC35C: ElementRole.UNKNOWN,     # Hyperlink -> mapped below
    0xC35D: ElementRole.IMAGE,       # Image
    0xC35E: ElementRole.LISTITEM,    # ListItem
    0xC35F: ElementRole.LISTITEM,    # List
    0xC360: ElementRole.MENU,        # Menu
    0xC361: ElementRole.UNKNOWN,     # MenuBar
    0xC362: ElementRole.MENUITEM,    # MenuItem
    0xC363: ElementRole.PANE,        # Pane
    0xC364: ElementRole.PROGRESSBAR, # ProgressBar
    0xC365: ElementRole.RADIO,       # RadioButton
    0xC366: ElementRole.SCROLLBAR,   # ScrollBar
    0xC367: ElementRole.UNKNOWN,     # Separator
    0xC368: ElementRole.SLIDER,      # Slider
    0xC369: ElementRole.UNKNOWN,     # Spinner
    0xC36A: ElementRole.UNKNOWN,     # SplitButton
    0xC36B: ElementRole.STATUSBAR,   # StatusBar
    0xC36C: ElementRole.TAB,         # Tab
    0xC36D: ElementRole.TABPANEL,    # TabItem
    0xC36E: ElementRole.TEXT,        # Text
    0xC36F: ElementRole.TOOLBAR,     # ToolBar
    0xC370: ElementRole.UNKNOWN,     # ToolTip
    0xC371: ElementRole.TREE,        # Tree
    0xC372: ElementRole.TREEITEM,    # TreeItem
    0xC373: ElementRole.WINDOW,      # Window
    0xC374: ElementRole.UNKNOWN,     # AppBar
    0xC375: ElementRole.UNKNOWN,     # SemanticZoom
}


def _get_uia():
    """Get or create persistent UIA instance."""
    global _uia_instance
    if _uia_instance is not None:
        return _uia_instance

    try:
        import comtypes.client
        import comtypes.gen

        try:
            interface = comtypes.gen.UIAutomationClient.IUIAutomation
        except AttributeError:
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            interface = module.IUIAutomation

        _uia_instance = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=interface,
        )
        return _uia_instance
    except Exception as e:
        logger.warning("[UIA] Cannot create UIA instance: %s", e)
        return None


def capture(
    hwnd: Optional[int] = None,
    app_type: AppType = AppType.WIN32,
) -> LayerResult:
    """
    Capture UIA element tree for window.
    Main entry point for Layer 1.
    """
    # Skip UIA for apps where it's useless
    if app_type == AppType.GAME:
        return LayerResult(
            layer=CaptureLayer.UIA,
            success=False,
            error="UIA skipped for GAME app type",
            elapsed_ms=0,
        )

    start = time.monotonic()

    elements = run_with_timeout(
        _capture_impl,
        args=(hwnd, app_type),
        timeout=8.0,
        default=[],
        layer_name="uia"
    )

    elapsed = (time.monotonic() - start) * 1000
    logger.debug(
        "[UIA] Captured %d elements in %.0fms",
        len(elements), elapsed
    )

    return LayerResult(
        layer=CaptureLayer.UIA,
        success=len(elements) > 0,
        elements=elements,
        elapsed_ms=elapsed,
        confidence=0.95,
    )


def _capture_impl(
    hwnd: Optional[int],
    app_type: AppType,
) -> list[UIElement]:
    """Internal UIA capture -- runs in timeout wrapper."""
    elements = []

    try:
        uia = _get_uia()
        if uia is None:
            return []

        # Get root element
        if hwnd:
            root = uia.ElementFromHandle(hwnd)
        else:
            root = None
            foreground_hwnd = _get_foreground_hwnd()
            if foreground_hwnd:
                try:
                    root = uia.ElementFromHandle(foreground_hwnd)
                except Exception:
                    root = None
            if root is None:
                root = uia.GetRootElement()

        if root is None:
            return []

        # Walk element tree
        walker = uia.CreateTreeWalker(
            uia.ControlViewCondition
        )
        _walk_uia_tree(
            root, elements, depth=0,
            max_depth=_MAX_DEPTH,
            max_elements=_MAX_ELEMENTS,
            parent_name="",
            parent_role="",
            walker=walker,
        )

    except ImportError:
        logger.warning(
            "[UIA] comtypes not available. "
            "Install: pip install comtypes"
        )
    except Exception as e:
        logger.error("[UIA] Capture failed: %s", e)

    return elements


def _create_uia_client():
    """Compatibility wrapper for callers that still request a UIA client."""
    return _get_uia()


def _get_foreground_hwnd() -> Optional[int]:
    """Return the active foreground window handle when available."""
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return int(hwnd) or None
    except Exception:
        return None


def _walk_uia_tree(
    element,
    results: list,
    depth: int,
    max_depth: int,
    max_elements: int,
    parent_name: str,
    parent_role: str,
    walker,
    sibling_index: int = 0,
) -> None:
    """Recursively walk UIA element tree."""
    if len(results) >= max_elements or depth > max_depth:
        return

    try:
        ui_el = _convert_uia_element(
            element, parent_name, parent_role, sibling_index
        )
        if ui_el:
            results.append(ui_el)
            new_parent_name = ui_el.name
            new_parent_role = ui_el.role.value
        else:
            new_parent_name = parent_name
            new_parent_role = parent_role

        # Walk children
        try:
            child = walker.GetFirstChildElement(element)
            child_idx = 0

            while child and len(results) < max_elements:
                _walk_uia_tree(
                    child, results,
                    depth + 1, max_depth, max_elements,
                    new_parent_name, new_parent_role,
                    walker,
                    child_idx,
                )
                child = walker.GetNextSiblingElement(child)
                child_idx += 1

        except Exception:
            pass

    except Exception as e:
        logger.debug("[UIA] Element walk error: %s", e)


def _convert_uia_element(
    element,
    parent_name: str,
    parent_role: str,
    sibling_index: int,
) -> Optional[UIElement]:
    """Convert a UIA element to UIElement dataclass."""
    try:
        # Get basic properties
        name = ""
        try:
            name = element.CurrentName or ""
        except Exception:
            pass

        control_type = 0
        try:
            control_type = element.CurrentControlType
        except Exception:
            pass

        role = _UIA_ROLE_MAP.get(control_type, ElementRole.UNKNOWN)

        # Handle Edit controls (text inputs)
        if control_type == 0xC358:
            role = ElementRole.INPUT

        # Handle Hyperlink
        if control_type == 0xC35C:
            role = ElementRole.LINK

        # Skip completely empty unknown elements
        if role == ElementRole.UNKNOWN and not name:
            return None

        # Get bounding rectangle
        bbox = None
        try:
            rect = element.CurrentBoundingRectangle
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w >= _MIN_ELEMENT_SIZE and h >= _MIN_ELEMENT_SIZE:
                bbox = BoundingBox(
                    x=rect.left, y=rect.top,
                    width=w, height=h
                )
        except Exception:
            pass

        # Check visibility
        is_offscreen = True
        try:
            is_offscreen = bool(element.CurrentIsOffscreen)
        except Exception:
            pass

        if is_offscreen:
            return None

        # Check enabled state
        is_enabled = True
        try:
            is_enabled = bool(element.CurrentIsEnabled)
        except Exception:
            pass

        # Check keyboard focus
        is_focused = False
        try:
            is_focused = bool(element.CurrentHasKeyboardFocus)
        except Exception:
            pass

        # Get current value (for inputs)
        value = ""
        try:
            value_pattern = element.GetCurrentPattern(10002)
            if value_pattern:
                value = value_pattern.CurrentValue or ""
        except Exception:
            pass

        # Get automation ID
        automation_id = ""
        try:
            automation_id = element.CurrentAutomationId or ""
        except Exception:
            pass

        # Get keyboard shortcut
        shortcut = ""
        try:
            shortcut = element.CurrentAccessKey or ""
        except Exception:
            pass

        # Determine action capabilities
        is_clickable = role in (
            ElementRole.BUTTON,
            ElementRole.LINK,
            ElementRole.MENUITEM,
            ElementRole.TAB,
            ElementRole.TREEITEM,
            ElementRole.LISTITEM,
            ElementRole.CHECKBOX,
            ElementRole.RADIO,
        )
        is_typeable = role in (
            ElementRole.INPUT,
            ElementRole.TEXTAREA,
        )
        is_focusable = True
        try:
            is_focusable = bool(element.CurrentIsKeyboardFocusable)
        except Exception:
            pass

        # Get runtime ID for hands engine
        runtime_id = None
        try:
            rid = element.GetRuntimeId()
            if rid:
                runtime_id = ".".join(str(x) for x in rid)
        except Exception:
            pass

        return UIElement(
            name=name.strip(),
            role=role,
            value=value,
            bbox=bbox,
            confidence=0.95,
            source=ElementSource.UIA,
            is_clickable=is_clickable and is_enabled,
            is_typeable=is_typeable and is_enabled,
            is_focusable=is_focusable,
            is_visible=not is_offscreen,
            is_enabled=is_enabled,
            is_focused=is_focused,
            keyboard_shortcut=shortcut,
            parent_name=parent_name,
            parent_role=parent_role,
            sibling_index=sibling_index,
            runtime_id=runtime_id,
            automation_id=automation_id,
        )

    except Exception as e:
        logger.debug("[UIA] Element convert failed: %s", e)
        return None
