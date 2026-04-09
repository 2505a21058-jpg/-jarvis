from threading import Lock


class SessionContext:
    def __init__(self):
        self._lock = Lock()
        self.active_app = ""
        self.last_action = ""

    def set_app(self, app_name: str):
        normalized = str(app_name).strip().lower()
        with self._lock:
            self.active_app = normalized
            self.last_action = f"open:{normalized}" if normalized else ""

    def get_app(self) -> str:
        with self._lock:
            return self.active_app

    def reset(self):
        with self._lock:
            self.active_app = ""
            self.last_action = ""


SESSION_CONTEXT = SessionContext()
