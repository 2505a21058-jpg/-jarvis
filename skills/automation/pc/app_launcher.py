"""
skills/automation/pc/app_launcher.py

Reliable app launching with window detection.
Replaces: Popen -> sleep(2) -> assume it worked.

Strategy order: Win32 ShellExecute -> subprocess -> OS file association
Window detection via EnumWindows instead of fixed sleep().
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Optional

logger = logging.getLogger("jarvis.pc.launcher")

_APP_ALIASES: dict[str, str] = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "notepad": "notepad",
    "notepad++": "notepad++",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "discord": "discord",
    "slack": "slack",
    "spotify": "spotify",
    "telegram": "telegram",
    "calculator": "calc",
    "terminal": "cmd",
    "cmd": "cmd",
    "powershell": "powershell",
    "explorer": "explorer",
    "file explorer": "explorer",
    "paint": "mspaint",
    "vlc": "vlc",
    "obs": "obs64",
}

_WINDOW_ALIASES: dict[str, list[str]] = {
    "chrome": ["chrome", "google chrome"],
    "firefox": ["firefox"],
    "msedge": ["edge", "microsoft edge"],
    "code": ["code", "visual studio code", "vs code", "vscode"],
    "cmd": ["cmd", "command prompt", "terminal"],
    "powershell": ["powershell", "terminal"],
    "explorer": ["explorer", "file explorer"],
    "winword": ["word", "microsoft word"],
    "excel": ["excel", "microsoft excel"],
    "powerpnt": ["powerpoint", "microsoft powerpoint"],
    "calc": ["calc", "calculator"],
    "mspaint": ["paint", "mspaint"],
    "obs64": ["obs", "obs studio"],
}

_BROWSER_APPS = {
    "youtube",
    "gmail",
    "google",
    "facebook",
    "twitter",
    "instagram",
    "reddit",
    "whatsapp web",
}


def resolve_app(app_name: str) -> Optional[str]:
    """Resolve user app name to executable. Returns None for browser-based apps."""
    lower = str(app_name or "").lower().strip()
    if lower in _BROWSER_APPS:
        return None
    return _APP_ALIASES.get(lower, lower)


def is_browser_app(app_name: str) -> bool:
    return str(app_name or "").lower().strip() in _BROWSER_APPS


def _window_fragments(app_name: str) -> list[str]:
    normalized = str(app_name or "").lower().strip()
    resolved = resolve_app(normalized)
    fragments: list[str] = []

    for value in (normalized, resolved):
        if value and value not in fragments:
            fragments.append(value)

    if resolved:
        for alias in _WINDOW_ALIASES.get(resolved, []):
            alias_lower = alias.lower().strip()
            if alias_lower and alias_lower not in fragments:
                fragments.append(alias_lower)

    return fragments


def launch_app(app_name: str, wait_for_window: bool = True) -> str:
    """
    Launch app using best available strategy.
    Strategy order: Win32 ShellExecute -> subprocess -> OS file association
    """
    resolved = resolve_app(app_name)
    if resolved is None:
        return f"'{app_name}' is web-based - use browser skill"

    logger.info("[LAUNCHER] %s -> %s", app_name, resolved)

    launched = _launch_win32(resolved) or _launch_subprocess(resolved) or _launch_start(resolved)
    if not launched:
        return f"Could not open '{app_name}' - is it installed?"

    if wait_for_window:
        found = _wait_for_window(app_name, timeout=10)
        if found:
            bring_to_front(app_name)
        else:
            logger.debug("[LAUNCHER] Window not detected for %s (still ok)", app_name)

    return f"Opened {app_name}"


def _launch_win32(executable: str) -> bool:
    try:
        import ctypes

        result = ctypes.windll.shell32.ShellExecuteW(None, "open", executable, None, None, 1)
        return int(result) > 32
    except Exception as exc:
        logger.debug("[LAUNCHER] Win32 failed: %s", exc)
        return False


def _launch_subprocess(executable: str) -> bool:
    try:
        subprocess.Popen(
            [executable],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as exc:
        logger.debug("[LAUNCHER] subprocess failed: %s", exc)
        return False


def _launch_start(executable: str) -> bool:
    try:
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            startfile(executable)
        else:
            subprocess.Popen(
                [executable],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True
    except Exception as exc:
        logger.debug("[LAUNCHER] file association launch failed: %s", exc)
        return False


def _wait_for_window(app_name: str, timeout: int = 10) -> bool:
    start = time.time()
    fragments = _window_fragments(app_name)
    while time.time() - start < timeout:
        if any(_window_exists(fragment) for fragment in fragments):
            return True
        time.sleep(0.5)
    return False


wait_for_window = _wait_for_window


def _window_exists(fragment: str) -> bool:
    try:
        import ctypes
        import ctypes.wintypes

        found = []

        def _cb(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    if fragment in buf.value.lower():
                        found.append(True)
            return True

        wnd_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.c_int)
        ctypes.windll.user32.EnumWindows(wnd_enum_proc(_cb), 0)
        return bool(found)
    except Exception:
        return False


def bring_to_front(app_name: str) -> bool:
    try:
        import ctypes
        import ctypes.wintypes

        hwnds = []
        fragments = _window_fragments(app_name)

        def _cb(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.lower()
                    if any(fragment in title for fragment in fragments):
                        hwnds.append(hwnd)
            return True

        wnd_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.c_int)
        ctypes.windll.user32.EnumWindows(wnd_enum_proc(_cb), 0)
        if hwnds:
            ctypes.windll.user32.ShowWindow(hwnds[0], 9)
            ctypes.windll.user32.SetForegroundWindow(hwnds[0])
            return True
    except Exception as exc:
        logger.warning("[LAUNCHER] bring_to_front failed: %s", exc)
    return False
