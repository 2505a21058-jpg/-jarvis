import logging

logger = logging.getLogger("jarvis.skills.focus")


def focus_app(app_name: str = "") -> bool:
    """Find a visible window whose title matches *app_name* and bring it to foreground."""
    if not app_name:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        fragments = [app_name.lower().strip()]
        if fragments[0].endswith(".exe"):
            fragments.append(fragments[0][:-4])
        raw = "".join(c for c in fragments[0] if c.isalnum())
        if raw and raw not in fragments:
            fragments.append(raw)

        found: list[int] = []

        def _cb(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.lower()
                    if any(fragment in title for fragment in fragments):
                        found.append(hwnd)
            return True

        wnd_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_int)
        ctypes.windll.user32.EnumWindows(wnd_enum_proc(_cb), 0)

        if found:
            ctypes.windll.user32.ShowWindow(found[0], 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(found[0])
            logger.debug("Focused window for '%s' (hwnd=%s)", app_name, found[0])
            return True

        logger.debug("No visible window found for '%s'", app_name)
        return False
    except Exception as exc:
        logger.debug("Could not focus app '%s': %s", app_name, exc)
        return False
