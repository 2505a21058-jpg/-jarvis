from threading import Lock


class SessionContext:
    def __init__(self):
        self._lock = Lock()
        self.active_app = ""
        self.active_platform = ""
        self.last_action = ""

    def set_app(self, app_name: str, platform: str | None = None):
        normalized = str(app_name).strip().lower()
        with self._lock:
            self.active_app = normalized
            if platform is not None:
                self.active_platform = str(platform).strip().lower()
            elif normalized in {"chrome", "browser", "google"}:
                self.active_platform = ""
            elif normalized:
                self.active_platform = ""
            self.last_action = f"open:{normalized}" if normalized else ""

    def get_app(self) -> str:
        with self._lock:
            return self.active_app

    def set_platform(self, platform: str):
        normalized = str(platform).strip().lower()
        with self._lock:
            self.active_platform = normalized

    def get_platform(self) -> str:
        with self._lock:
            return self.active_platform

    def reset(self):
        with self._lock:
            self.active_app = ""
            self.active_platform = ""
            self.last_action = ""


SESSION_CONTEXT = SessionContext()
