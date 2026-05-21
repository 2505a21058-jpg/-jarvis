from __future__ import annotations

from rawvision.output.schema import AppType, CaptureLayer


def test_process_monitor_capture_wraps_process_info(monkeypatch):
    from rawvision.capture import process_monitor

    info = process_monitor.ProcessInfo(
        hwnd=101,
        pid=202,
        process_name="chrome.exe",
        window_title="Example - Chrome",
        app_type=AppType.CHROME,
        app_friendly_name="Chrome",
        cdp_available=True,
        cdp_port=9222,
    )

    monkeypatch.setattr(process_monitor, "_capture_impl", lambda hwnd=None: info)

    result = process_monitor.capture(hwnd=101)

    assert result.layer is CaptureLayer.PROCESS_MONITOR
    assert result.success is True
    assert result.elements == ()
    assert result.app_type is AppType.CHROME
    assert result.app_name == "Chrome"
    assert result.app_pid == 202
    assert result.window_title == "Example - Chrome"
    assert result.cdp_port == 9222
    assert result.raw_data["process_info"]["hwnd"] == 101


def test_process_monitor_classifies_known_process_types():
    from rawvision.capture import process_monitor

    chrome = process_monitor.ProcessInfo(process_name="msedge.exe")
    process_monitor._classify_app(chrome)
    assert chrome.app_type is AppType.CHROME
    assert chrome.app_friendly_name == "Edge"
    assert chrome.uia_support_level == "partial"

    office = process_monitor.ProcessInfo(process_name="excel.exe")
    process_monitor._classify_app(office)
    assert office.app_type is AppType.OFFICE
    assert office.app_friendly_name == "Excel"
    assert office.uia_support_level == "full"

    terminal = process_monitor.ProcessInfo(process_name="pwsh.exe")
    process_monitor._classify_app(terminal)
    assert terminal.app_type is AppType.TERMINAL
    assert terminal.uia_support_level == "partial"
