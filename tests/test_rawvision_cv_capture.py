from __future__ import annotations

import numpy as np

from rawvision.output.schema import BoundingBox, CaptureLayer, ElementSource


def test_cv_capture_reads_text_from_changed_regions_only(monkeypatch):
    from rawvision.capture import cv_capture

    image = np.zeros((20, 30, 3), dtype=np.uint8)
    region = BoundingBox(x=10, y=5, width=8, height=6)

    monkeypatch.setattr(cv_capture, "_get_ocr_reader", lambda: ("fake", object()))
    monkeypatch.setattr(
        cv_capture,
        "_run_ocr",
        lambda crop, _engine_name, _engine: [
            cv_capture.OCRDetection(
                text="OK",
                confidence=0.88,
                bbox=BoundingBox(x=1, y=2, width=3, height=2),
            )
        ],
    )
    monkeypatch.setattr(cv_capture, "_detect_ui_regions", lambda crop, offset: [])

    result = cv_capture.capture(image=image, changed_regions=[region])

    assert result.layer is CaptureLayer.OCR
    assert result.success is True
    assert result.raw_data["regions_processed"] == 1
    assert result.raw_data["ocr_engine"] == "fake"
    assert len(result.elements) == 1

    element = result.elements[0]
    assert element.name == "OK"
    assert element.source is ElementSource.OCR
    assert element.bbox == BoundingBox(x=11, y=7, width=3, height=2)
    assert element.is_visible is True


def test_cv_capture_skips_when_no_changed_regions(monkeypatch):
    from rawvision.capture import cv_capture

    image = np.zeros((20, 30, 3), dtype=np.uint8)

    def fail_reader():
        raise AssertionError("OCR reader should not load without regions")

    monkeypatch.setattr(cv_capture, "_get_ocr_reader", fail_reader)

    result = cv_capture.capture(image=image, changed_regions=[])

    assert result.layer is CaptureLayer.OCR
    assert result.success is True
    assert result.elements == ()
    assert result.raw_data["regions_processed"] == 0


def test_cv_capture_fails_gracefully_without_frame(monkeypatch):
    from rawvision.capture import cv_capture

    monkeypatch.setattr(cv_capture, "_capture_frame", lambda monitor=None: None)

    result = cv_capture.capture(changed_regions=[BoundingBox(0, 0, 5, 5)])

    assert result.layer is CaptureLayer.OCR
    assert result.success is False
    assert "No image" in result.error
    assert result.elements == ()


def test_cv_capture_parses_paddle_and_easyocr_results():
    from rawvision.capture import cv_capture

    paddle = [
        [
            [
                [[1, 2], [6, 2], [6, 5], [1, 5]],
                ("Save", 0.91),
            ]
        ]
    ]
    easy = [
        (
            [[3, 4], [8, 4], [8, 7], [3, 7]],
            "Open",
            0.82,
        )
    ]

    paddle_detection = cv_capture._parse_paddle_result(paddle)[0]
    easy_detection = cv_capture._parse_easyocr_result(easy)[0]

    assert paddle_detection.text == "Save"
    assert paddle_detection.confidence == 0.91
    assert paddle_detection.bbox == BoundingBox(1, 2, 5, 3)
    assert easy_detection.text == "Open"
    assert easy_detection.confidence == 0.82
    assert easy_detection.bbox == BoundingBox(3, 4, 5, 3)


def test_cv_capture_falls_back_to_easyocr_when_paddle_unavailable(monkeypatch):
    import builtins

    from rawvision.capture import cv_capture

    real_import = builtins.__import__

    class FakeEasyOCR:
        class Reader:
            def __init__(self, languages, gpu=False):
                self.languages = languages
                self.gpu = gpu

    def fake_import(name, *args, **kwargs):
        if name == "paddleocr":
            raise ImportError("no paddle")
        if name == "easyocr":
            return FakeEasyOCR
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(cv_capture, "_ocr_reader", None)
    monkeypatch.setattr(cv_capture, "_ocr_reader_name", "")

    engine_name, reader = cv_capture._get_ocr_reader()

    assert engine_name == "easyocr"
    assert reader.languages == ["en"]
    assert reader.gpu is False
