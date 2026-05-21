"""
rawvision/fusion/formatter.py
Builds ScreenContext from all LayerResults.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from rawvision.output.schema import AppType, CaptureLayer, LayerResult, ScreenContext
from rawvision.fusion.arbitrator import score_all
from rawvision.fusion.deduplicator import deduplicate
from rawvision.utils.spatial import visual_importance_score

logger = logging.getLogger("rawvision.fusion.formatter")

_LAYER_ORDER = {
    CaptureLayer.PROCESS_MONITOR: 0,
    CaptureLayer.UIA: 1,
    CaptureLayer.CDP: 2,
    CaptureLayer.PIXEL_DIFF: 3,
    CaptureLayer.OCR: 4,
    CaptureLayer.SCREENSHOT: 5,
}


def build_context(
    layer_results: list[LayerResult],
    capture_start: float,
    max_tokens: Optional[int] = None,
) -> ScreenContext:
    """Build ScreenContext from all layer outputs."""
    app_name = ""
    app_type = AppType.UNKNOWN
    window_title = ""
    app_pid = 0
    cdp_port = None
    screenshot_b64 = None
    layers_used = []
    layers_failed = []
    cdp_url = ""

    for r in _ordered_results(layer_results):
        if r.success:
            layers_used.append(r.layer)
        else:
            layers_failed.append(r.layer)

        if r.layer == CaptureLayer.PROCESS_MONITOR:
            app_name = r.app_name or app_name
            app_type = r.app_type or app_type
            window_title = r.window_title or window_title
            app_pid = r.app_pid or app_pid
            cdp_port = r.cdp_port or cdp_port

        if r.layer == CaptureLayer.CDP:
            cdp_url = str(r.raw_data.get("url", "") or "")

        if r.layer == CaptureLayer.SCREENSHOT:
            screenshot_b64 = r.raw_data.get("screenshot_b64")

    all_elements = []
    for r in layer_results:
        if r.layer != CaptureLayer.PROCESS_MONITOR:
            all_elements.extend(r.elements)

    deduped = deduplicate(all_elements)
    scored = score_all(deduped)
    sorted_elements = sorted(scored, key=lambda e: -visual_importance_score(e))
    sorted_elements = _enforce_token_budget(sorted_elements, max_tokens)

    capture_ms = (time.monotonic() - capture_start) * 1000

    return ScreenContext(
        app_name=app_name or "Unknown",
        app_type=app_type,
        window_title=window_title,
        app_pid=app_pid,
        cdp_port=cdp_port,
        cdp_url=cdp_url,
        elements=tuple(sorted_elements),
        captured_at=time.time(),
        capture_ms=capture_ms,
        layers_used=tuple(layers_used),
        layers_failed=tuple(layers_failed),
        screenshot_b64=screenshot_b64,
    )


def format_results(
    layer_results: list[LayerResult],
    max_tokens: Optional[int] = 800,
) -> ScreenContext:
    """Compatibility wrapper for older callers."""
    return build_context(
        layer_results=layer_results,
        capture_start=time.monotonic(),
        max_tokens=max_tokens,
    )


def _ordered_results(layer_results: list[LayerResult]) -> list[LayerResult]:
    return sorted(
        layer_results or [],
        key=lambda result: _LAYER_ORDER.get(result.layer, 99),
    )


def _enforce_token_budget(
    elements: list,
    max_tokens: Optional[int],
) -> list:
    if not max_tokens:
        return elements

    kept = []
    used = 0
    for element in elements:
        estimate = max(1, len(element.to_llm_str()) // 4)
        if kept and used + estimate > max_tokens:
            break
        kept.append(element)
        used += estimate
    return kept
