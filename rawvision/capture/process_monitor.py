"""
rawvision/capture/process_monitor.py

Layer 0 — Process Monitor.
Reads OS metadata about the foreground window.
Runs in 2ms. Informs all other capture layers.

Output:
- What app is in focus
- What TYPE it is (Chrome/Electron/Office/Win32/Terminal/Game)
- Whether UIA will work
- Whether CDP is available and on which port
- Window handle for Win32 operations

This is the cheapest layer and runs unconditionally first.
Every other layer uses its output to decide what to do.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from rawvision.output.schema import AppType, LayerResult, CaptureLayer
from rawvision.utils.timeout import run_with_timeout

logger = logging.getLogger("rawvision.capture.process_monitor")

# Known Electron app process names
_ELECTRON_PROCESSES = {
    "code": "vscode",
    "code.exe": "vscode",
    "discord": "discord",
    "discord.exe": "discord",
    "slack": "slack",
    "slack.exe": "slack",
    "spotify": "spotify",
    "spotify.exe": "spotify",
    "notion": "notion",
    "notion.exe": "notion",
    "obsidian": "obsidian",
    "obsidian.exe": "obsidian",
    "whatsapp": "whatsapp",
    "whatsapp.exe": "whatsapp",
    "figma": "figma",
    "figma.exe": "figma",
}

# Known Electron CDP ports
_ELECTRON_CDP_PORTS = {
    "vscode":   [9229, 9230, 9231],
    "discord":  [13172, 13173],
    "spotify":  [4370, 4371, 4380],
    "slack":    [9222, 9223],
    "notion":   [9222, 9223],
    "whatsapp": [9222, 9223],
    "obsidian": [9222, 9223],
}

# Chrome/Edge process names
_BROWSER_PROCESSES = {
    "chrome.exe", "chromium.exe",
    "msedge.exe", "brave.exe",
    "opera.exe", "vivaldi.exe",
}

# Office process names
_OFFICE_PROCESSES = {
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "outlook.exe": "Outlook",
    "onenote.exe": "OneNote",
    "msaccess.exe": "Access",
}

# Terminal process names
_TERMINAL_PROCESSES = {
    "cmd.exe", "powershell.exe",
    "windowsterminal.exe", "wt.exe",
    "pwsh.exe", "bash.exe",
    "wsl.exe", "ubuntu.exe",
    "mintty.exe", "conhost.exe",
}

# Game engine indicators
_GAME_INDICATORS = {
    "unity", "unreal", "godot",
    "steam.exe", "epicgameslauncher.exe",
}


@dataclass
class ProcessInfo:
    """
    Information about the foreground window's process.
    Output of Layer 0.
    """
    hwnd: int = 0
    pid: int = 0
    process_name: str = ""
    window_title: str = ""
    app_type: AppType = AppType.UNKNOWN
    app_friendly_name: str = ""

    # UIA support
    uia_supported: bool = True
    uia_support_level: str = "unknown"  # full/partial/none

    # CDP availability
    cdp_available: bool = False
    cdp_port: Optional[int] = None

    # Window state
    is_fullscreen: bool = False
    is_minimized: bool = False
    is_elevated: bool = False  # running as admin

    # Timing
    detected_at: float = field(default_factory=time.time)
    elapsed_ms: float = 0.0


def capture(hwnd: Optional[int] = None) -> LayerResult:
    """
    Capture process info for foreground window.
    Main entry point for Layer 0.

    hwnd: specific window handle, or None for foreground
    """
    start = time.monotonic()

    result = run_with_timeout(
        _capture_impl,
        args=(hwnd,),
        timeout=2.0,
        default=None,
        layer_name="process_monitor"
    )

    elapsed = (time.monotonic() - start) * 1000

    if result is None:
        return LayerResult(
            layer=CaptureLayer.PROCESS_MONITOR,
            success=False,
            error="Process monitor timed out or failed",
            elapsed_ms=elapsed,
        )

    return LayerResult(
        layer=CaptureLayer.PROCESS_MONITOR,
        success=True,
        elements=[],  # Layer 0 produces no elements
        raw_data={"process_info": result.__dict__},
        elapsed_ms=elapsed,
        app_type=result.app_type,
        app_name=result.app_friendly_name or result.process_name,
        app_pid=result.pid,
        window_title=result.window_title,
        cdp_port=result.cdp_port,
    )


def _capture_impl(hwnd: Optional[int] = None) -> Optional[ProcessInfo]:
    """Internal implementation — runs in timeout wrapper."""
    info = ProcessInfo()

    try:
        import ctypes
        import ctypes.wintypes

        # Get foreground window if no hwnd specified
        if hwnd is None:
            hwnd = ctypes.windll.user32.GetForegroundWindow()

        if not hwnd:
            logger.debug("[PROCESS] No foreground window")
            return info

        info.hwnd = hwnd

        # Get window title
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            info.window_title = buf.value

        # Get process ID
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(
            hwnd, ctypes.byref(pid)
        )
        info.pid = pid.value

        # Get process name
        info.process_name = _get_process_name(info.pid)

        # Classify app type
        _classify_app(info)

        # Check window state
        info.is_minimized = bool(
            ctypes.windll.user32.IsIconic(hwnd)
        )

        # Check if fullscreen
        info.is_fullscreen = _is_fullscreen(hwnd)

        # Find CDP port if applicable
        if info.app_type in (AppType.CHROME, AppType.ELECTRON):
            info.cdp_port = _find_cdp_port(info)
            info.cdp_available = info.cdp_port is not None

        logger.debug(
            "[PROCESS] %s | type=%s | cdp=%s | title=%s",
            info.process_name,
            info.app_type.value,
            info.cdp_port,
            info.window_title[:50]
        )

    except Exception as e:
        logger.warning("[PROCESS] Capture failed: %s", e)

    return info


def _get_process_name(pid: int) -> str:
    """Get process executable name from PID."""
    try:
        import ctypes
        import ctypes.wintypes

        PROCESS_QUERY_INFO = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_INFO, False, pid
        )
        if not handle:
            return ""

        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)

        # QueryFullProcessImageName
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size)
        ):
            ctypes.windll.kernel32.CloseHandle(handle)
            full_path = buf.value
            return full_path.split("\\")[-1].lower()

        ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass

    # Fallback: psutil
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.name().lower()
    except Exception:
        return ""


def _classify_app(info: ProcessInfo) -> None:
    """Classify app type and set UIA support level."""
    proc = info.process_name.lower()
    title = info.window_title.lower()

    # Chrome/Edge browser
    if proc in _BROWSER_PROCESSES:
        info.app_type = AppType.CHROME
        info.app_friendly_name = "Chrome"
        if "edge" in proc:
            info.app_friendly_name = "Edge"
        info.uia_support_level = "partial"
        return

    # Electron apps
    if proc in _ELECTRON_PROCESSES:
        app_name = _ELECTRON_PROCESSES[proc]
        info.app_type = AppType.ELECTRON
        info.app_friendly_name = app_name.title()
        info.uia_support_level = "partial"
        return

    # Generic Electron detection
    if _is_electron_process(info.pid):
        info.app_type = AppType.ELECTRON
        info.app_friendly_name = proc.replace(".exe", "").title()
        info.uia_support_level = "partial"
        return

    # Office apps
    if proc in _OFFICE_PROCESSES:
        info.app_type = AppType.OFFICE
        info.app_friendly_name = _OFFICE_PROCESSES[proc]
        info.uia_support_level = "full"
        return

    # Terminal
    if proc in _TERMINAL_PROCESSES:
        info.app_type = AppType.TERMINAL
        info.app_friendly_name = proc.replace(".exe", "").title()
        info.uia_support_level = "partial"
        return

    # Game detection
    if any(g in proc for g in _GAME_INDICATORS):
        info.app_type = AppType.GAME
        info.app_friendly_name = proc.replace(".exe", "").title()
        info.uia_support_level = "none"
        return

    # UWP detection (from window class)
    if _is_uwp_window(info.hwnd):
        info.app_type = AppType.UWP
        info.uia_support_level = "full"
        return

    # Default: native Win32
    info.app_type = AppType.WIN32
    info.app_friendly_name = proc.replace(".exe", "").title()
    info.uia_support_level = "full"


def _is_electron_process(pid: int) -> bool:
    """
    Detect Electron apps by checking for Chromium
    helper processes as children.
    """
    try:
        import psutil
        proc = psutil.Process(pid)
        children = proc.children(recursive=False)
        for child in children[:5]:  # check first 5 children only
            child_name = child.name().lower()
            if any(n in child_name for n in
                   ("renderer", "gpu", "chromium", "chrome")):
                return True
    except Exception:
        pass
    return False


def _is_uwp_window(hwnd: int) -> bool:
    """Detect UWP (Universal Windows Platform) windows."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
        window_class = buf.value
        return "ApplicationFrameWindow" in window_class
    except Exception:
        return False


def _is_fullscreen(hwnd: int) -> bool:
    """Detect if window is fullscreen."""
    try:
        import ctypes
        import ctypes.wintypes

        # Get window rect
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

        # Get screen resolution
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)

        w = rect.right - rect.left
        h = rect.bottom - rect.top

        return (abs(w - screen_w) < 5 and
                abs(h - screen_h) < 5)
    except Exception:
        return False


def _find_cdp_port(info: ProcessInfo) -> Optional[int]:
    """Find CDP debug port for Chrome/Electron process."""
    import urllib.request

    # Chrome standard port
    if info.app_type == AppType.CHROME:
        ports_to_try = [9222, 9223, 9224]
    else:
        # Electron — try known ports for this app
        app_lower = (info.app_friendly_name or "").lower()
        ports_to_try = _ELECTRON_CDP_PORTS.get(app_lower, [9229, 9222])

    for port in ports_to_try:
        try:
            url = f"http://localhost:{port}/json/version"
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return port
        except Exception:
            continue

    return None
