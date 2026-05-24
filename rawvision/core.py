"""
rawvision/core.py

RawVision orchestrator.
Runs all capture layers in parallel.
Builds ScreenContext from results.
Main public API entry point.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
import logging
import time
from typing import Callable, Optional

from rawvision.capture import (
    cv_capture,
    dom_capture,
    pixel_diff,
    process_monitor,
    screenshot_capture,
    uia_capture,
)
from rawvision.fusion.formatter import build_context
from rawvision.output.schema import AppType, BoundingBox, CaptureLayer, LayerResult, ScreenContext

logger = logging.getLogger("rawvision.core")


class RawVision:
    """
    Main entry point for RawVision.

    Usage:
        context = RawVision.capture()
        print(context.summary)
        print(context.to_llm())

        # For LLM injection:
        prompt = f"Current screen:\\n{context.to_llm(max_tokens=500)}"

        # For computer use agent:
        el = context.find("Search", actionable_only=True)
        diff = before.diff(after)
    """

    def __init__(
        self,
        max_workers: int = 5,
        max_tokens: Optional[int] = 800,
        include_screenshot: bool = True,
    ):
        self.max_workers = max(1, int(max_workers))
        self.max_tokens = max_tokens
        self.include_screenshot = include_screenshot

    def capture(
        self=None,
        hwnd: Optional[int] = None,
        include_screenshot: Optional[bool] = None,
        max_tokens: Optional[int] = None,
    ) -> ScreenContext:
        """
        Capture current screen state.
        Runs all layers in parallel.
        Returns ScreenContext.

        include_screenshot: also capture base64 screenshot
                            (needed for vision model fallback)
        max_tokens: if set, trims stored element context to the budget
        """
        if isinstance(self, RawVision):
            max_workers = self.max_workers
            include_ss = self.include_screenshot if include_screenshot is None else bool(include_screenshot)
            token_budget = self.max_tokens if max_tokens is None else max_tokens
        else:
            if self is not None and hwnd is None:
                hwnd = self
            max_workers = 5
            include_ss = bool(include_screenshot) if include_screenshot is not None else False
            token_budget = max_tokens

        return _capture_once(
            hwnd=hwnd,
            include_screenshot=include_ss,
            max_tokens=token_budget,
            max_workers=max_workers,
        )

    @contextmanager
    def session(self=None):
        """
        Context manager for multi-capture sessions.
        Reuses pixel diff baseline across captures.
        Cleans up on exit.
        """
        target = self if isinstance(self, RawVision) else RawVision
        try:
            yield target
        finally:
            _reset_session_state()


def _capture_once(
    hwnd: Optional[int],
    include_screenshot: bool,
    max_tokens: Optional[int],
    max_workers: int,
) -> ScreenContext:
    start = time.monotonic()

    pm_result = _safe_layer(
        CaptureLayer.PROCESS_MONITOR,
        process_monitor.capture,
        hwnd=hwnd,
    )
    layer_results = [pm_result]

    app_type = pm_result.app_type or AppType.UNKNOWN
    process_info = dict(pm_result.raw_data.get("process_info", {}))
    target_hwnd = int(process_info.get("hwnd") or hwnd or 0) or None
    cdp_port = pm_result.cdp_port
    electron_app = (
        str(process_info.get("app_friendly_name") or "")
        if app_type == AppType.ELECTRON
        else ""
    )

    futures = {}
    executor = ThreadPoolExecutor(
        max_workers=max(1, int(max_workers or 5)),
        thread_name_prefix="rawvision",
    )

    def _submit(layer: CaptureLayer, fn, **kw):
        try:
            future = executor.submit(_safe_layer, layer, fn, **kw)
            futures[future] = layer
        except RuntimeError:
            layer_results.append(
                LayerResult(layer=layer, success=False, error="interpreter shutting down")
            )

    try:
        if app_type != AppType.GAME:
            _submit(CaptureLayer.UIA, uia_capture.capture, hwnd=target_hwnd, app_type=app_type)

        if app_type in (AppType.CHROME, AppType.ELECTRON):
            _submit(CaptureLayer.CDP, dom_capture.capture, cdp_port=cdp_port, app_type=app_type, electron_app=electron_app)

        _submit(CaptureLayer.PIXEL_DIFF, pixel_diff.capture)

        if include_screenshot:
            _submit(CaptureLayer.SCREENSHOT, screenshot_capture.capture)

        done, pending = wait(futures, timeout=6.0)
        for future in done:
            layer_results.append(future.result())
        for future in pending:
            layer = futures[future]
            future.cancel()
            layer_results.append(
                LayerResult(
                    layer=layer,
                    success=False,
                    error=f"{layer.value} timed out",
                )
            )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    pixel_result = next(
        (result for result in layer_results if result.layer == CaptureLayer.PIXEL_DIFF),
        None,
    )
    regions = _changed_regions(pixel_result)
    if regions:
        layer_results.append(
            _safe_layer(
                CaptureLayer.OCR,
                cv_capture.capture,
                changed_regions=regions,
                image=pixel_result.raw_data.get("full_frame") if pixel_result else None,
            )
        )

    context = build_context(layer_results, start, max_tokens=max_tokens)

    elapsed = (time.monotonic() - start) * 1000
    logger.info(
        "[RAWVISION] Captured %d elements in %.0fms | app=%s type=%s layers=%s",
        len(context.elements),
        elapsed,
        context.app_name,
        context.app_type.value,
        ",".join(layer.value for layer in context.layers_used),
    )

    return context


def _changed_regions(pixel_result: Optional[LayerResult]) -> list[BoundingBox]:
    if not pixel_result or not pixel_result.success:
        return []

    raw_regions = (
        pixel_result.raw_data.get("changed_regions")
        or pixel_result.raw_data.get("changed_region_dicts")
        or ()
    )
    regions: list[BoundingBox] = []
    for region in raw_regions:
        if isinstance(region, BoundingBox):
            regions.append(region)
        elif isinstance(region, dict):
            bbox = BoundingBox.from_dict(region)
            if bbox:
                regions.append(bbox)
    return regions


def _safe_layer(
    layer: CaptureLayer,
    fn: Callable,
    **kwargs,
) -> LayerResult:
    try:
        result = fn(**kwargs)
        if isinstance(result, LayerResult):
            return result
        return LayerResult(
            layer=layer,
            success=False,
            error=f"Layer {layer.value} returned invalid result",
        )
    except Exception as exc:
        logger.warning("[CORE] Layer %s failed: %s", layer.value, exc)
        return LayerResult(
            layer=layer,
            success=False,
            error=str(exc),
        )


def _reset_session_state() -> None:
    try:
        pixel_diff.reset_state()
        return
    except Exception:
        pass

    try:
        pixel_diff._previous_frame = None
        pixel_diff._prev_frame = None
    except Exception:
        pass
