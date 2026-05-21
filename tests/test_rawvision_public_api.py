from __future__ import annotations

from rawvision.output.schema import ScreenContext


def test_rawvision_public_api_exports_core_types():
    import rawvision
    from rawvision import RawVision

    assert rawvision.RawVision is RawVision
    assert rawvision.ScreenContext is ScreenContext
    assert callable(rawvision.capture)
    assert callable(rawvision.session)
    assert "RawVision" in rawvision.__all__
    assert "ScreenContext" in rawvision.__all__


def test_rawvision_public_capture_uses_default_instance(monkeypatch):
    import rawvision

    expected = ScreenContext(app_name="Test")

    class FakeRawVision:
        def capture(self, **kwargs):
            assert kwargs == {"hwnd": 123}
            return expected

    monkeypatch.setattr(rawvision, "RawVision", FakeRawVision)

    assert rawvision.capture(hwnd=123) is expected
