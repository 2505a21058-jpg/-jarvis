"""
agent/screenshot_agent/_perception.py

Screenshot-only perception layer for when UIA/DOM/accessibility
are unavailable. Takes a screenshot, runs OCR, and asks a vision
model for a description — returns a structured ScreenRepr.

Zoom: automatically re-captures regions where OCR confidence is
low (< 0.7) and merges results for higher accuracy.
"""

from __future__ import annotations

import base64
import io
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("jarvis.screenshot_agent.perception")

_OCR_CONFIDENCE_THRESHOLD = 0.7
_DEFAULT_MAX_WIDTH = 1280
_PNG_COMPRESS_LEVEL = 6

_ocr_reader = None
_ocr_attempted = False


@dataclass
class OCRText:
    text: str
    x: int
    y: int
    w: int
    h: int
    confidence: float


@dataclass
class ScreenRepr:
    screenshot_b64: str
    width: int
    height: int
    ocr_texts: list[OCRText] = field(default_factory=list)
    vision_description: str = ""
    zoom_region: Optional[tuple[int, int, int, int]] = None
    capture_ms: float = 0.0


def _get_ocr_reader():
    global _ocr_reader, _ocr_attempted
    if _ocr_reader is not None:
        return _ocr_reader
    if _ocr_attempted:
        return None
    _ocr_attempted = True
    try:
        from paddleocr import PaddleOCR
        _ocr_reader = PaddleOCR(use_textline_orientation=True, lang="en")
        return _ocr_reader
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("PaddleOCR init failed: %s", exc)
    try:
        import easyocr
        _ocr_reader = easyocr.Reader(["en"], gpu=False)
        return _ocr_reader
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("EasyOCR init failed: %s", exc)
    logger.warning("No OCR engine available (install paddleocr or easyocr)")
    return None


def _run_ocr(image_bytes: bytes) -> list[OCRText]:
    reader = _get_ocr_reader()
    if reader is None:
        return []
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        import numpy as np
        arr = np.array(img.convert("RGB"))
        results = []
        if hasattr(reader, "ocr"):
            raw = reader.ocr(arr)
            if raw and raw[0]:
                for detection in raw[0]:
                    bbox, (text, conf) = detection
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    x = int(sum(xs) / len(xs))
                    y = int(sum(ys) / len(ys))
                    w = int(max(xs) - min(xs))
                    h = int(max(ys) - min(ys))
                    results.append(OCRText(text=str(text), x=x, y=y, w=w, h=h, confidence=float(conf)))
        else:
            raw = reader.readtext(arr)
            for bbox, text, conf in raw:
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                x = int(sum(xs) / len(xs))
                y = int(sum(ys) / len(ys))
                w = int(max(xs) - min(xs))
                h = int(max(ys) - min(ys))
                results.append(OCRText(text=str(text), x=x, y=y, w=w, h=h, confidence=float(conf)))
        return results
    except Exception as exc:
        logger.debug("OCR failed: %s", exc)
        return []


def _take_screenshot(region: Optional[tuple[int, int, int, int]] = None, max_width: int = _DEFAULT_MAX_WIDTH) -> Optional[tuple[bytes, int, int]]:
    try:
        import mss
        import numpy as np
        from PIL import Image

        with mss.mss() as sct:
            if region:
                x1, y1, x2, y2 = region
                monitor = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
                raw = sct.grab(monitor)
            else:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)

            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            orig_w, orig_h = img.size

            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True, compress_level=_PNG_COMPRESS_LEVEL)
            return buf.getvalue(), orig_w, orig_h
    except ImportError:
        logger.debug("mss not available for screenshot")
        return None
    except Exception as exc:
        logger.debug("Screenshot failed: %s", exc)
        return None


def _ask_vision(prompt: str, image_b64: str) -> str:
    try:
        from models.gemma import call_gemma_vision_json
        result = call_gemma_vision_json(prompt=prompt, image_b64=image_b64, system="")
        if isinstance(result, dict):
            return result.get("description") or result.get("response") or str(result)
        return str(result or "")
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("Gemma vision unavailable: %s", exc)

    try:
        import requests
        from config import OLLAMA_GENERATE_URL, VISION_MODEL, VISION_REQUEST_TIMEOUT_SECONDS
        resp = requests.post(
            OLLAMA_GENERATE_URL,
            json={"model": VISION_MODEL, "prompt": prompt, "images": [image_b64], "stream": False},
            timeout=VISION_REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except Exception as exc:
        logger.debug("Ollama vision unavailable: %s", exc)

    return ""


def _describe_screen(screenshot_b64: str) -> str:
    prompt = (
        "Describe this computer screen in 1-2 concise sentences. "
        "What application is visible? What buttons, text fields, "
        "or content areas are on screen?"
    )
    return _ask_vision(prompt, screenshot_b64)


def perceive(zoom_region: Optional[tuple[int, int, int, int]] = None) -> Optional[ScreenRepr]:
    start = time.monotonic()

    raw_bytes, orig_w, orig_h = _take_screenshot(region=zoom_region) or (None, 0, 0)
    if raw_bytes is None:
        return None

    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    ocr_results = _run_ocr(raw_bytes)
    vision_desc = _describe_screen(b64)

    repr = ScreenRepr(
        screenshot_b64=b64,
        width=orig_w,
        height=orig_h,
        ocr_texts=ocr_results,
        vision_description=vision_desc,
        zoom_region=zoom_region,
        capture_ms=(time.monotonic() - start) * 1000,
    )

    if zoom_region is None:
        low_conf = [t for t in ocr_results if t.confidence < _OCR_CONFIDENCE_THRESHOLD]
        if low_conf:
            margin = 20
            texts_by_region = _cluster_texts(low_conf, margin=100)
            for region_texts in texts_by_region:
                xs = [t.x - t.w // 2 for t in region_texts]
                ys = [t.y - t.h // 2 for t in region_texts]
                xe = [t.x + t.w // 2 for t in region_texts]
                ye = [t.y + t.h // 2 for t in region_texts]
                zoom_x1 = max(0, min(xs) - margin)
                zoom_y1 = max(0, min(ys) - margin)
                zoom_x2 = min(orig_w, max(xe) + margin)
                zoom_y2 = min(orig_h, max(ye) + margin)
                region = (zoom_x1, zoom_y1, zoom_x2, zoom_y2)
                logger.debug("Auto-zooming into region %s for low-confidence OCR", region)
                zoomed = perceive(zoom_region=region)
                if zoomed:
                    repr.ocr_texts.extend(zoomed.ocr_texts)
                    if zoomed.vision_description and not repr.vision_description:
                        repr.vision_description = zoomed.vision_description

    logger.debug("Perception: %d OCR texts, %d ms", len(repr.ocr_texts), repr.capture_ms)
    return repr


def _cluster_texts(texts: list[OCRText], margin: int = 100) -> list[list[OCRText]]:
    if not texts:
        return []
    clusters: list[list[OCRText]] = []
    used = set()
    for i, a in enumerate(texts):
        if i in used:
            continue
        cluster = [a]
        used.add(i)
        for j, b in enumerate(texts):
            if j in used:
                continue
            if abs(a.x - b.x) < margin and abs(a.y - b.y) < margin:
                cluster.append(b)
                used.add(j)
        clusters.append(cluster)
    return clusters
