"""
rawvision/capture/screenshot_capture.py

Layer 5 -- screenshot fallback.
Captures a framebuffer image with mss, resizes/compresses it, and returns
a base64 PNG string for vision model consumption.
"""

from __future__ import annotations

import base64
import io
import logging
import time
from typing import Optional

from rawvision.output.schema import CaptureLayer, LayerResult
from rawvision.utils.timeout import run_with_timeout

logger = logging.getLogger("rawvision.capture.screenshot")

_DEFAULT_MAX_WIDTH = 1280
_PNG_COMPRESS_LEVEL = 6


def capture(
    image=None,
    monitor: Optional[dict[str, int]] = None,
    max_width: int = _DEFAULT_MAX_WIDTH,
) -> LayerResult:
    """Capture and encode a resized PNG screenshot."""
    start = time.monotonic()
    result = run_with_timeout(
        _capture_impl,
        args=(image, monitor, max_width),
        timeout=3.0,
        default={
            "success": False,
            "error": "Screenshot timed out",
            "screenshot_b64": "",
            "size": None,
            "original_size": None,
        },
        layer_name="screenshot",
    )
    elapsed = (time.monotonic() - start) * 1000

    return LayerResult(
        layer=CaptureLayer.SCREENSHOT,
        success=bool(result.get("success")),
        raw_data={
            "screenshot_b64": str(result.get("screenshot_b64") or ""),
            "size": result.get("size"),
            "original_size": result.get("original_size"),
            "mime_type": "image/png",
        },
        error=str(result.get("error") or ""),
        elapsed_ms=elapsed,
        confidence=0.45,
    )


def _capture_impl(image, monitor: Optional[dict[str, int]], max_width: int) -> dict:
    frame = _normalize_image(image if image is not None else _capture_frame(monitor))
    if frame is None:
        return {
            "success": False,
            "error": "No screenshot frame captured",
            "screenshot_b64": "",
            "size": None,
            "original_size": None,
        }

    encoded, size, original_size = _encode_png_b64(frame, max_width=max_width)
    return {
        "success": bool(encoded),
        "error": "" if encoded else "Screenshot encoding failed",
        "screenshot_b64": encoded,
        "size": size,
        "original_size": original_size,
    }


def _capture_frame(monitor: Optional[dict[str, int]] = None):
    try:
        import mss

        with mss.mss() as sct:
            target = monitor or sct.monitors[1]
            return sct.grab(target)
    except Exception as exc:
        logger.debug("[SCREENSHOT] mss capture failed: %s", exc)
        return None


def _normalize_image(image):
    try:
        import numpy as np

        arr = np.asarray(image)
        if arr.ndim == 2:
            arr = arr[:, :, None]
        if arr.ndim != 3:
            return None
        if arr.shape[2] >= 3:
            arr = arr[:, :, :3]
        return arr.astype("uint8", copy=False)
    except Exception as exc:
        logger.debug("[SCREENSHOT] Image normalize failed: %s", exc)
        return None


def _encode_png_b64(frame, max_width: int = _DEFAULT_MAX_WIDTH) -> tuple[str, tuple[int, int], tuple[int, int]]:
    try:
        from PIL import Image

        height, width = frame.shape[:2]
        original_size = (int(width), int(height))
        image = Image.fromarray(frame)

        max_width = max(1, int(max_width or _DEFAULT_MAX_WIDTH))
        if width > max_width:
            ratio = max_width / float(width)
            new_size = (max_width, max(1, int(round(height * ratio))))
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            image = image.resize(new_size, resample=resample)

        buffer = io.BytesIO()
        image.save(
            buffer,
            format="PNG",
            optimize=True,
            compress_level=_PNG_COMPRESS_LEVEL,
        )
        return (
            base64.b64encode(buffer.getvalue()).decode("ascii"),
            image.size,
            original_size,
        )
    except Exception as exc:
        logger.debug("[SCREENSHOT] PNG encode failed: %s", exc)
        return "", (0, 0), (0, 0)
