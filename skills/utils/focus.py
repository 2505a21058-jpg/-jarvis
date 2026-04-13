import time


def focus_app(app_name: str = "") -> bool:
    try:
        import pyautogui

        pyautogui.hotkey("alt", "tab")
        time.sleep(0.2)
        return True
    except Exception:
        return False
