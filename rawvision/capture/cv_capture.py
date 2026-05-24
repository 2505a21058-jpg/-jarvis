"""
rawvision/capture/cv_capture.py

Layer 4 -- OCR and lightweight computer vision.
Runs PaddleOCR on changed pixel regions, with EasyOCR as fallback.

Output: list[UIElement] with source=ElementSource.OCR.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Sequence

from rawvision.output.schema import (
    BoundingBox,
    CaptureLayer,
    ElementRole,
    ElementSource,
    LayerResult,
    UIElement,
)
from rawvision.utils.timeout import run_with_timeout

logger = logging.getLogger("rawvision.capture.cv")

_OCR_TIMEOUT = 5.0
_OCR_CONFIDENCE_BASE = 0.71
_MAX_REGIONS = 30
_MIN_TEXT_CONFIDENCE = 0.25
_MIN_UI_REGION_AREA = 64

_ocr_reader = None
_ocr_reader_name = ""


@dataclass(frozen=True)
class OCRDetection:
    text: str
    confidence: float
    bbox: BoundingBox


def capture(
    changed_regions: Optional[Sequence[BoundingBox | dict]] = None,
    image=None,
    monitor: Optional[dict[str, int]] = None,
) -> LayerResult:
    """
    Run OCR on changed regions only.

    image may be supplied by the orchestrator. If omitted, this layer captures
    a framebuffer snapshot with mss.
    """
    start = time.monotonic()
    result = run_with_timeout(
        _capture_impl,
        args=(changed_regions, image, monitor),
        timeout=_OCR_TIMEOUT,
        default={
            "success": False,
            "error": "OCR timed out",
            "elements": (),
            "regions_processed": 0,
            "ocr_engine": "",
        },
        layer_name="ocr",
    )
    elapsed = (time.monotonic() - start) * 1000

    return LayerResult(
        layer=CaptureLayer.OCR,
        success=bool(result.get("success")),
        elements=tuple(result.get("elements") or ()),
        raw_data={
            "regions_processed": int(result.get("regions_processed") or 0),
            "ocr_engine": str(result.get("ocr_engine") or ""),
        },
        error=str(result.get("error") or ""),
        elapsed_ms=elapsed,
        confidence=_OCR_CONFIDENCE_BASE,
    )


def _capture_impl(
    changed_regions: Optional[Sequence[BoundingBox | dict]],
    image,
    monitor: Optional[dict[str, int]],
) -> dict:
    regions = _coerce_regions(changed_regions)
    if not regions:
        return {
            "success": True,
            "error": "",
            "elements": (),
            "regions_processed": 0,
            "ocr_engine": "",
        }

    frame = _normalize_image(image if image is not None else _capture_frame(monitor))
    if frame is None:
        return {
            "success": False,
            "error": "No image available for OCR",
            "elements": (),
            "regions_processed": 0,
            "ocr_engine": "",
        }

    try:
        engine_name, engine = _get_ocr_reader()
    except Exception as exc:
        logger.warning("[OCR] No OCR engine available: %s", exc)
        return {
            "success": False,
            "error": f"No OCR engine available: {exc}",
            "elements": (),
            "regions_processed": 0,
            "ocr_engine": "",
        }

    elements: list[UIElement] = []
    processed = 0

    for region in regions[:_MAX_REGIONS]:
        crop = _crop_region(frame, region)
        if crop is None:
            continue
        processed += 1

        detections = _run_ocr(crop, engine_name, engine)
        for detection in detections:
            element = _detection_to_element(detection, region)
            if element:
                elements.append(element)

        elements.extend(_detect_ui_regions(crop, region))

    return {
        "success": True,
        "error": "",
        "elements": tuple(elements),
        "regions_processed": processed,
        "ocr_engine": engine_name,
    }


def _coerce_regions(
    regions: Optional[Sequence[BoundingBox | dict]],
) -> list[BoundingBox]:
    coerced = []
    for region in regions or ():
        if isinstance(region, BoundingBox):
            bbox = region
        elif isinstance(region, dict):
            bbox = BoundingBox.from_dict(region)
        else:
            bbox = None
        if bbox and bbox.width > 0 and bbox.height > 0:
            coerced.append(bbox)
    return coerced


def _capture_frame(monitor: Optional[dict[str, int]] = None):
    try:
        import mss

        with mss.mss() as sct:
            target = monitor or sct.monitors[1]
            return sct.grab(target)
    except Exception as exc:
        logger.debug("[OCR] Frame capture failed: %s", exc)
        return None


def _normalize_image(image):
    try:
        import numpy as np

        arr = np.asarray(image)
        if arr.ndim == 2:
            return arr[:, :, None].astype(np.uint8, copy=False)
        if arr.ndim != 3:
            return None
        if arr.shape[2] >= 3:
            return arr[:, :, :3].astype(np.uint8, copy=False)
        return arr.astype(np.uint8, copy=False)
    except Exception as exc:
        logger.debug("[OCR] Image normalize failed: %s", exc)
        return None


def _crop_region(frame, region: BoundingBox):
    try:
        height, width = frame.shape[:2]
        left = max(0, min(region.x, width))
        top = max(0, min(region.y, height))
        right = max(left, min(region.right, width))
        bottom = max(top, min(region.bottom, height))
        if right <= left or bottom <= top:
            return None
        return frame[top:bottom, left:right]
    except Exception as exc:
        logger.debug("[OCR] Region crop failed: %s", exc)
        return None


def _get_ocr_reader():
    global _ocr_reader, _ocr_reader_name

    if _ocr_reader is not None:
        return _ocr_reader_name, _ocr_reader

    try:
        from paddleocr import PaddleOCR

        try:
            _ocr_reader = PaddleOCR(lang="en")
        except TypeError:
            _ocr_reader = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        _ocr_reader_name = "paddleocr"
        return _ocr_reader_name, _ocr_reader
    except Exception as paddle_exc:
        logger.debug("[OCR] PaddleOCR unavailable: %s", paddle_exc)

    try:
        import easyocr

        _ocr_reader = easyocr.Reader(["en"], gpu=False)
        _ocr_reader_name = "easyocr"
        return _ocr_reader_name, _ocr_reader
    except Exception as easy_exc:
        raise RuntimeError("install paddleocr or easyocr") from easy_exc


def _run_ocr(crop, engine_name: str, engine) -> list[OCRDetection]:
    if engine_name == "paddleocr":
        try:
            return _parse_paddle_result(engine.ocr(crop, cls=True))
        except TypeError:
            return _parse_paddle_result(engine.ocr(crop))
    if engine_name == "easyocr":
        return _parse_easyocr_result(engine.readtext(crop))
    return []


def _parse_paddle_result(result) -> list[OCRDetection]:
    detections: list[OCRDetection] = []
    for item in _flatten_paddle_result(result):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        points = item[0]
        text_info = item[1]
        if not isinstance(text_info, (list, tuple)) or len(text_info) < 2:
            continue
        text = str(text_info[0] or "").strip()
        confidence = _coerce_confidence(text_info[1])
        detection = _make_detection(text, confidence, points)
        if detection:
            detections.append(detection)
    return detections


def _flatten_paddle_result(result):
    if not result:
        return []
    if isinstance(result, dict):
        return result.get("rec_boxes", []) or result.get("dt_polys", []) or []
    if (
        isinstance(result, list)
        and len(result) == 1
        and isinstance(result[0], list)
        and result[0]
        and isinstance(result[0][0], (list, tuple))
    ):
        return result[0]
    return result


def _parse_easyocr_result(result) -> list[OCRDetection]:
    detections: list[OCRDetection] = []
    for item in result or ():
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        points, text, confidence = item[0], str(item[1] or "").strip(), item[2]
        detection = _make_detection(text, _coerce_confidence(confidence), points)
        if detection:
            detections.append(detection)
    return detections


def _make_detection(text: str, confidence: float, points) -> Optional[OCRDetection]:
    if not text or confidence < _MIN_TEXT_CONFIDENCE:
        return None
    bbox = _points_to_bbox(points)
    if not bbox:
        return None
    return OCRDetection(text=text, confidence=confidence, bbox=bbox)


def _points_to_bbox(points) -> Optional[BoundingBox]:
    try:
        if not points:
            return None
        xs = []
        ys = []
        for point in points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
        if not xs or not ys:
            return None
        min_x = int(min(xs))
        min_y = int(min(ys))
        max_x = int(max(xs))
        max_y = int(max(ys))
        return BoundingBox(
            x=min_x,
            y=min_y,
            width=max(1, max_x - min_x),
            height=max(1, max_y - min_y),
        )
    except Exception:
        return None


def _coerce_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _detection_to_element(
    detection: OCRDetection,
    region: BoundingBox,
) -> Optional[UIElement]:
    bbox = BoundingBox(
        x=region.x + detection.bbox.x,
        y=region.y + detection.bbox.y,
        width=detection.bbox.width,
        height=detection.bbox.height,
    )
    return UIElement(
        name=detection.text,
        role=ElementRole.TEXT,
        bbox=bbox,
        confidence=max(0.1, min(0.89, _OCR_CONFIDENCE_BASE * detection.confidence)),
        source=ElementSource.OCR,
        is_visible=True,
        is_enabled=True,
    )


def _detect_ui_regions(crop, offset: BoundingBox) -> list[UIElement]:
    boxes = _detect_ui_boxes_cv2(crop)
    if boxes is None:
        boxes = _detect_ui_boxes_numpy(crop)

    elements = []
    for idx, box in enumerate(boxes):
        bbox = BoundingBox(
            x=offset.x + box.x,
            y=offset.y + box.y,
            width=box.width,
            height=box.height,
        )
        elements.append(
            UIElement(
                name="",
                role=ElementRole.UNKNOWN,
                bbox=bbox,
                confidence=0.45,
                source=ElementSource.OCR,
                is_visible=True,
                is_enabled=True,
                sibling_index=idx,
            )
        )
    return elements


def _detect_ui_boxes_cv2(crop) -> Optional[list[BoundingBox]]:
    try:
        import cv2
        import numpy as np

        arr = np.asarray(crop)
        if arr.ndim == 3:
            gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            gray = arr
        edges = cv2.Canny(gray, 50, 150)
        contours, _hierarchy = cv2.findContours(
            edges,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        boxes = []
        for contour in contours[:100]:
            x, y, width, height = cv2.boundingRect(contour)
            if width * height >= _MIN_UI_REGION_AREA:
                boxes.append(BoundingBox(x=int(x), y=int(y), width=int(width), height=int(height)))
        return boxes[:20]
    except Exception:
        return None


def _detect_ui_boxes_numpy(crop) -> list[BoundingBox]:
    try:
        import numpy as np

        arr = np.asarray(crop)
        if arr.ndim == 3:
            gray = arr[:, :, :3].mean(axis=2)
        elif arr.ndim == 2:
            gray = arr
        else:
            return []

        dark = gray < 64
        ys, xs = np.where(dark)
        if len(xs) < _MIN_UI_REGION_AREA:
            return []
        bbox = BoundingBox(
            x=int(xs.min()),
            y=int(ys.min()),
            width=int(xs.max() - xs.min() + 1),
            height=int(ys.max() - ys.min() + 1),
        )
        if bbox.area < _MIN_UI_REGION_AREA:
            return []
        return [bbox]
    except Exception:
        return []
