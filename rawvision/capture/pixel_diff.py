"""
rawvision/capture/pixel_diff.py

Layer 3 -- framebuffer diff capture.
Detects changed screen regions since the last capture.

Capture backend:
  1. dxcam (primary, fast Windows framebuffer capture)
  2. mss   (fallback, cross-platform screenshot capture)

Output: LayerResult.raw_data["changed_regions"] as tuple[BoundingBox, ...].
Used by Layer 4 so OCR can run only on changed regions.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from rawvision.output.schema import BoundingBox, CaptureLayer, LayerResult
from rawvision.utils.timeout import run_with_timeout

logger = logging.getLogger("rawvision.capture.pixel_diff")

_DIFF_THRESHOLD = 25
_MIN_REGION_AREA = 4
_MAX_REGIONS = 50

_previous_frame = None


def capture(monitor: Optional[dict[str, int]] = None) -> LayerResult:
    """
    Capture framebuffer and return changed regions since previous capture.

    The first successful capture seeds internal state and returns no regions.
    """
    start = time.monotonic()
    result = run_with_timeout(
        _capture_impl,
        args=(monitor,),
        timeout=2.0,
        default={
            "success": False,
            "error": "Pixel diff timed out",
            "changed_regions": (),
            "frame_size": None,
        },
        layer_name="pixel_diff",
    )
    elapsed = (time.monotonic() - start) * 1000
    regions = tuple(result.get("changed_regions") or ())

    return LayerResult(
        layer=CaptureLayer.PIXEL_DIFF,
        success=bool(result.get("success")),
        raw_data={
            "changed_regions": regions,
            "changed_region_dicts": tuple(region.to_dict() for region in regions),
            "frame_size": result.get("frame_size"),
        },
        error=str(result.get("error") or ""),
        elapsed_ms=elapsed,
        confidence=0.86,
    )


def reset_state() -> None:
    """Clear the previous framebuffer used for diffing."""
    global _previous_frame
    _previous_frame = None


def _capture_impl(monitor: Optional[dict[str, int]]) -> dict[str, Any]:
    global _previous_frame

    frame = _capture_frame(monitor=monitor)
    if frame is None:
        return {
            "success": False,
            "error": "No framebuffer captured",
            "changed_regions": (),
            "frame_size": None,
        }

    frame = _normalize_frame(frame)
    if frame is None:
        return {
            "success": False,
            "error": "Framebuffer format unsupported",
            "changed_regions": (),
            "frame_size": None,
        }

    frame_size = (int(frame.shape[1]), int(frame.shape[0]))
    if _previous_frame is None:
        _previous_frame = frame.copy()
        return {
            "success": True,
            "error": "",
            "changed_regions": (),
            "frame_size": frame_size,
        }

    if _previous_frame.shape != frame.shape:
        _previous_frame = frame.copy()
        return {
            "success": True,
            "error": "",
            "changed_regions": (
                BoundingBox(x=0, y=0, width=frame_size[0], height=frame_size[1]),
            ),
            "frame_size": frame_size,
        }

    changed_regions = _diff_frames(_previous_frame, frame)
    _previous_frame = frame.copy()

    return {
        "success": True,
        "error": "",
        "changed_regions": tuple(changed_regions),
        "frame_size": frame_size,
    }


def _capture_frame(monitor: Optional[dict[str, int]] = None):
    """Capture one framebuffer using dxcam first, then mss."""
    frame = _capture_frame_dxcam(monitor)
    if frame is not None:
        return frame
    return _capture_frame_mss(monitor)


def _capture_frame_dxcam(monitor: Optional[dict[str, int]] = None):
    try:
        import dxcam

        camera = dxcam.create(output_idx=0)
        if camera is None:
            return None

        region = _monitor_to_region(monitor)
        if region:
            return camera.grab(region=region)
        return camera.grab()
    except Exception as exc:
        logger.debug("[PIXEL] dxcam capture failed: %s", exc)
        return None


def _capture_frame_mss(monitor: Optional[dict[str, int]] = None):
    try:
        import mss

        with mss.mss() as sct:
            target = monitor or sct.monitors[1]
            shot = sct.grab(target)
            return shot
    except Exception as exc:
        logger.debug("[PIXEL] mss capture failed: %s", exc)
        return None


def _monitor_to_region(
    monitor: Optional[dict[str, int]]
) -> Optional[tuple[int, int, int, int]]:
    if not monitor:
        return None
    left = int(monitor.get("left", monitor.get("x", 0)))
    top = int(monitor.get("top", monitor.get("y", 0)))
    width = int(monitor.get("width", 0))
    height = int(monitor.get("height", 0))
    if width <= 0 or height <= 0:
        return None
    return (left, top, left + width, top + height)


def _normalize_frame(frame):
    try:
        import numpy as np

        arr = np.asarray(frame)
        if arr.ndim == 2:
            return arr[:, :, None].astype(np.uint8, copy=False)
        if arr.ndim != 3:
            return None
        if arr.shape[2] >= 3:
            return arr[:, :, :3].astype(np.uint8, copy=False)
        return arr.astype(np.uint8, copy=False)
    except Exception as exc:
        logger.debug("[PIXEL] Frame normalize failed: %s", exc)
        return None


def _diff_frames(previous, current) -> list[BoundingBox]:
    try:
        import numpy as np

        diff = np.abs(current.astype(np.int16) - previous.astype(np.int16))
        if diff.ndim == 3:
            changed = np.any(diff > _DIFF_THRESHOLD, axis=2)
        else:
            changed = diff > _DIFF_THRESHOLD

        return _mask_to_regions(changed)
    except Exception as exc:
        logger.debug("[PIXEL] Frame diff failed: %s", exc)
        return []


def _mask_to_regions(mask) -> list[BoundingBox]:
    regions = _mask_to_regions_cv2(mask)
    if regions is not None:
        return regions
    return _mask_to_regions_numpy(mask)


def _mask_to_regions_cv2(mask) -> Optional[list[BoundingBox]]:
    try:
        import cv2
        import numpy as np

        mask_u8 = np.asarray(mask, dtype=np.uint8)
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            mask_u8,
            connectivity=4,
        )

        regions: list[BoundingBox] = []
        for idx in range(1, count):
            x, y, width, height, area = stats[idx]
            if int(area) < _MIN_REGION_AREA:
                continue
            regions.append(
                BoundingBox(
                    x=int(x),
                    y=int(y),
                    width=int(width),
                    height=int(height),
                )
            )
            if len(regions) >= _MAX_REGIONS:
                break

        regions.sort(key=lambda region: region.area, reverse=True)
        return regions
    except Exception as exc:
        logger.debug("[PIXEL] OpenCV region extraction unavailable: %s", exc)
        return None


def _mask_to_regions_numpy(mask) -> list[BoundingBox]:
    try:
        import numpy as np

        visited = np.zeros(mask.shape, dtype=bool)
        height, width = mask.shape
        regions: list[BoundingBox] = []

        ys, xs = np.where(mask)
        for start_x, start_y in zip(xs, ys):
            if visited[start_y, start_x]:
                continue

            min_x = max_x = int(start_x)
            min_y = max_y = int(start_y)
            stack = [(int(start_x), int(start_y))]
            visited[start_y, start_x] = True
            area = 0

            while stack:
                x, y = stack.pop()
                area += 1
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y

                for nx, ny in (
                    (x - 1, y),
                    (x + 1, y),
                    (x, y - 1),
                    (x, y + 1),
                ):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    if visited[ny, nx] or not mask[ny, nx]:
                        continue
                    visited[ny, nx] = True
                    stack.append((nx, ny))

            if area >= _MIN_REGION_AREA:
                regions.append(
                    BoundingBox(
                        x=min_x,
                        y=min_y,
                        width=max_x - min_x + 1,
                        height=max_y - min_y + 1,
                    )
                )
                if len(regions) >= _MAX_REGIONS:
                    break

        regions.sort(key=lambda region: region.area, reverse=True)
        return regions
    except Exception as exc:
        logger.debug("[PIXEL] Mask region extraction failed: %s", exc)
        return []
