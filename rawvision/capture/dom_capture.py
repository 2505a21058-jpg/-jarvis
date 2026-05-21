"""
rawvision/capture/dom_capture.py

Layer 2 -- Chrome DevTools Protocol DOM/AX capture.
Reads accessibility tree from Chrome and Electron apps
via the Browser Harness (agent/harness/browser.py).

Works on:
  Chrome browser:   full AX tree, all elements
  Edge browser:     full AX tree
  Electron apps:    full AX tree (VS Code, Discord, Slack, etc.)
  Other apps:       not applicable

Speed: ~20-30ms for typical page.
Timeout: 4 seconds hard limit.

Output: list[UIElement] with source=ElementSource.CDP
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
import urllib.request
from typing import Any, Optional

from rawvision.output.schema import (
    AppType,
    CaptureLayer,
    ElementRole,
    ElementSource,
    LayerResult,
    UIElement,
)
from rawvision.utils.timeout import run_with_timeout

logger = logging.getLogger("rawvision.capture.dom")

_MAX_AX_NODES = 300
_CAPTURE_TIMEOUT = 4.0
_ASYNC_CAPTURE_TIMEOUT = 3.8

# CDP AX role to ElementRole mapping
_CDP_ROLE_MAP = {
    "button": ElementRole.BUTTON,
    "link": ElementRole.LINK,
    "textbox": ElementRole.INPUT,
    "searchbox": ElementRole.INPUT,
    "combobox": ElementRole.DROPDOWN,
    "listbox": ElementRole.DROPDOWN,
    "option": ElementRole.LISTITEM,
    "listitem": ElementRole.LISTITEM,
    "checkbox": ElementRole.CHECKBOX,
    "radio": ElementRole.RADIO,
    "menuitem": ElementRole.MENUITEM,
    "menu": ElementRole.MENU,
    "menubar": ElementRole.MENU,
    "toolbar": ElementRole.TOOLBAR,
    "tab": ElementRole.TAB,
    "tabpanel": ElementRole.TABPANEL,
    "dialog": ElementRole.DIALOG,
    "alertdialog": ElementRole.DIALOG,
    "alert": ElementRole.ALERT,
    "heading": ElementRole.HEADING,
    "img": ElementRole.IMAGE,
    "image": ElementRole.IMAGE,
    "text": ElementRole.TEXT,
    "statictext": ElementRole.TEXT,
    "paragraph": ElementRole.TEXT,
    "generic": ElementRole.UNKNOWN,
    "none": ElementRole.UNKNOWN,
    "application": ElementRole.WINDOW,
    "main": ElementRole.PANE,
    "navigation": ElementRole.TOOLBAR,
    "region": ElementRole.PANE,
    "contentinfo": ElementRole.PANE,
    "banner": ElementRole.TOOLBAR,
    "complementary": ElementRole.PANE,
    "form": ElementRole.GROUP,
    "group": ElementRole.GROUP,
    "tree": ElementRole.TREE,
    "treeitem": ElementRole.TREEITEM,
    "table": ElementRole.TABLE,
    "row": ElementRole.ROW,
    "cell": ElementRole.CELL,
    "columnheader": ElementRole.CELL,
    "rowheader": ElementRole.CELL,
    "progressbar": ElementRole.PROGRESSBAR,
    "slider": ElementRole.SLIDER,
    "spinbutton": ElementRole.SLIDER,
    "scrollbar": ElementRole.SCROLLBAR,
    "separator": ElementRole.UNKNOWN,
    "status": ElementRole.STATUSBAR,
    "log": ElementRole.UNKNOWN,
    "marquee": ElementRole.UNKNOWN,
    "timer": ElementRole.UNKNOWN,
    "tooltip": ElementRole.UNKNOWN,
    "switch": ElementRole.CHECKBOX,
    "gridcell": ElementRole.CELL,
    "grid": ElementRole.TABLE,
    "treegrid": ElementRole.TABLE,
    "feed": ElementRole.LISTITEM,
    "figure": ElementRole.IMAGE,
    "math": ElementRole.TEXT,
    "note": ElementRole.TEXT,
    "presentation": ElementRole.UNKNOWN,
    "document": ElementRole.DOCUMENT,
    "article": ElementRole.GROUP,
    "definition": ElementRole.TEXT,
    "term": ElementRole.TEXT,
}


def capture(
    cdp_port: Optional[int] = None,
    app_type: AppType = AppType.CHROME,
    electron_app: str = "",
) -> LayerResult:
    """
    Capture DOM/AX tree via CDP.
    Main entry point for Layer 2.
    """
    app_type = _coerce_app_type(app_type)

    # Only runs for browser/electron
    if app_type not in (AppType.CHROME, AppType.ELECTRON):
        return LayerResult(
            layer=CaptureLayer.CDP,
            success=False,
            error=f"CDP skipped for {app_type.value}",
            elapsed_ms=0,
            app_type=app_type,
        )

    start = time.monotonic()
    elements, url = run_with_timeout(
        _capture_sync,
        args=(cdp_port, app_type, electron_app),
        timeout=_CAPTURE_TIMEOUT,
        default=([], ""),
        layer_name="cdp",
    )

    elapsed = (time.monotonic() - start) * 1000
    logger.debug(
        "[DOM] Captured %d elements in %.0fms url=%s",
        len(elements), elapsed, url[:60]
    )

    return LayerResult(
        layer=CaptureLayer.CDP,
        success=len(elements) > 0,
        elements=elements,
        raw_data={"url": url},
        elapsed_ms=elapsed,
        confidence=0.93,
        app_type=app_type,
        cdp_port=cdp_port,
    )


def _coerce_app_type(app_type: AppType) -> AppType:
    if isinstance(app_type, AppType):
        return app_type
    try:
        return AppType(str(app_type).lower())
    except ValueError:
        return AppType.UNKNOWN


def _capture_sync(
    cdp_port: Optional[int],
    app_type: AppType,
    electron_app: str,
) -> tuple[list[UIElement], str]:
    """Run async CDP capture from sync code, including inside active event loops."""
    coroutine = asyncio.wait_for(
        _capture_async(cdp_port, app_type, electron_app),
        timeout=_ASYNC_CAPTURE_TIMEOUT,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(asyncio.run, coroutine)
        try:
            return future.result(timeout=_CAPTURE_TIMEOUT)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    return asyncio.run(coroutine)


async def _capture_async(
    cdp_port: Optional[int],
    app_type: AppType,
    electron_app: str,
) -> tuple[list[UIElement], str]:
    """Async CDP capture implementation."""
    from agent.harness.browser import get_harness

    port = cdp_port or 9222
    if app_type == AppType.CHROME and not _is_cdp_port_available(port):
        logger.debug("[DOM] CDP port %s not available", port)
        return [], ""

    harness = get_harness(port=port)

    # Get the right tab
    if app_type == AppType.ELECTRON and electron_app:
        tab = await asyncio.wait_for(
            harness.electron_tab(electron_app),
            timeout=2.0,
        )
    else:
        ready = await asyncio.wait_for(
            harness.ensure_ready(),
            timeout=2.0,
        )
        if not ready:
            return [], ""
        tab = await asyncio.wait_for(
            harness.active_tab(),
            timeout=2.0,
        )

    if not tab:
        logger.debug("[DOM] No tab available")
        return [], ""

    try:
        # Get current URL
        url = await asyncio.wait_for(tab.get_url(), timeout=1.0)

        # Get accessibility tree
        ax_result = await asyncio.wait_for(
            tab.get_ax_tree(), timeout=2.5
        )

        if not ax_result:
            return [], url

        # Parse AX nodes into UIElements
        nodes = ax_result.get("nodes", [])
        elements = _parse_ax_nodes(nodes, url)

        return elements, url

    except asyncio.TimeoutError:
        logger.warning("[DOM] CDP request timed out")
        return [], ""
    except Exception as e:
        logger.error("[DOM] Async capture failed: %s", e)
        return [], ""


def _parse_ax_nodes(
    nodes: list[dict],
    page_url: str,
) -> list[UIElement]:
    """Parse CDP AX tree nodes into UIElement list."""
    elements = []

    # Build node lookup for parent resolution.
    node_map = {node.get("nodeId"): node for node in nodes}
    parent_map = _build_parent_map(nodes)

    for sibling_index, node in enumerate(nodes[:_MAX_AX_NODES]):
        el = _convert_ax_node(node, node_map, parent_map, page_url, sibling_index)
        if el:
            elements.append(el)

    return elements


def _build_parent_map(nodes: list[dict]) -> dict[str, str]:
    parent_map = {}
    for node in nodes:
        node_id = node.get("nodeId")
        for child_id in node.get("childIds", []) or []:
            parent_map[child_id] = node_id
    return parent_map


def _is_cdp_port_available(port: int) -> bool:
    """Fast preflight so missing Chrome fails gracefully without launching."""
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/json/version",
            timeout=0.5,
        ) as response:
            return response.status == 200
    except Exception:
        return False


def _convert_ax_node(
    node: dict,
    node_map: dict,
    parent_map: dict,
    page_url: str,
    sibling_index: int = 0,
) -> Optional[UIElement]:
    """Convert CDP AX node to UIElement."""
    try:
        # Skip ignored/hidden nodes
        ignored = node.get("ignored", False)
        if ignored:
            return None

        # Get role
        role_str = _ax_value(node.get("role", ""))
        role = _CDP_ROLE_MAP.get(
            role_str.lower(), ElementRole.UNKNOWN
        )

        # Get name and top-level AX value
        name = _ax_value(node.get("name", ""))
        top_level_value = _ax_value(node.get("value", ""))

        # Get properties
        props = {}
        for prop in node.get("properties", []) or []:
            if isinstance(prop, dict):
                key = prop.get("name", "")
                props[key] = _ax_value(prop.get("value", ""))

        # Determine capabilities
        is_focused = bool(props.get("focused"))
        is_disabled = bool(props.get("disabled"))
        is_enabled = not is_disabled
        is_expanded = _optional_bool(props.get("expanded"))
        is_selected = _optional_bool(props.get("selected"))
        value = str(
            top_level_value
            or props.get("value")
            or props.get("valuetext")
            or ""
        )
        placeholder = str(props.get("placeholder") or "")
        description = str(
            _ax_value(node.get("description", ""))
            or props.get("description")
            or ""
        )
        keyboard_shortcut = str(
            props.get("keyshortcuts")
            or props.get("accesskey")
            or ""
        )

        # Action capabilities by role
        is_clickable = role in (
            ElementRole.BUTTON,
            ElementRole.LINK,
            ElementRole.MENUITEM,
            ElementRole.TAB,
            ElementRole.CHECKBOX,
            ElementRole.RADIO,
            ElementRole.LISTITEM,
            ElementRole.TREEITEM,
        )
        is_typeable = role in (
            ElementRole.INPUT,
            ElementRole.TEXTAREA,
        ) or role_str.lower() in ("textbox", "searchbox", "combobox")

        # Get CDP node IDs
        backend_node_id = node.get("backendDOMNodeId")
        node_id_str = str(node.get("nodeId", ""))

        # Get parent info
        parent_name = ""
        parent_role = ""
        parent_id = node.get("parentId") or parent_map.get(node.get("nodeId"))
        if parent_id and parent_id in node_map:
            parent_node = node_map[parent_id]
            parent_role = _ax_value(parent_node.get("role", ""))
            parent_name = _ax_value(parent_node.get("name", ""))

        # Skip if no useful content
        if (not name and not value and not placeholder
                and role == ElementRole.UNKNOWN):
            return None

        return UIElement(
            name=(name or value or placeholder).strip(),
            role=role,
            value=value,
            placeholder=placeholder,
            description=description,
            confidence=0.93,
            source=ElementSource.CDP,
            is_clickable=is_clickable and is_enabled,
            is_typeable=is_typeable and is_enabled,
            is_focusable=True,
            is_visible=True,
            is_enabled=is_enabled,
            is_focused=is_focused,
            is_expanded=is_expanded,
            is_selected=is_selected,
            keyboard_shortcut=keyboard_shortcut,
            parent_name=parent_name,
            parent_role=parent_role,
            sibling_index=sibling_index,
            cdp_node_id=backend_node_id,
            runtime_id=node_id_str,
            cdp_node_path=f"{page_url}#{node_id_str}",
        )

    except Exception as e:
        logger.debug("[DOM] Node convert failed: %s", e)
        return None


def _ax_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value", "")
    if value is None:
        return ""
    return value


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    return bool(value)
