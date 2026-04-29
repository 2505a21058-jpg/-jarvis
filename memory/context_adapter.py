"""
Compatibility adapter. Do NOT use for new code.
Provides SESSION_CONTEXT-compatible interface backed by agent State.
"""

from __future__ import annotations

import logging


logger = logging.getLogger("jarvis.context_adapter")

_state_ref = None  # set during startup


def set_state_ref(state) -> None:
    global _state_ref
    _state_ref = state


class _SessionContextProxy:
    """Mimics dict-style and legacy SessionContext access backed by unified State."""

    def _state(self):
        if _state_ref is None:
            logger.warning("SESSION_CONTEXT accessed before state initialized")
        return _state_ref

    def get(self, key, default=None):
        state = self._state()
        if state is None:
            return default
        if hasattr(state, key):
            return getattr(state, key)
        return state.ui_context.get(key, default)

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        state = self._state()
        if state is None:
            logger.warning("SESSION_CONTEXT write before state initialized")
            return
        if hasattr(state, key):
            setattr(state, key, value)
        else:
            state.ui_context[key] = value

    def __contains__(self, key):
        return self.get(key) is not None

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        state = self._state()
        if state is None:
            raise AttributeError(key)
        if hasattr(state, key):
            return getattr(state, key)
        if key in state.ui_context:
            return state.ui_context[key]
        raise AttributeError(key)

    def __setattr__(self, key, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return
        self.__setitem__(key, value)

    def set_app(self, app_name: str, platform: str | None = None):
        state = self._state()
        if state is None:
            return
        state.set_active_app(app_name)
        if platform is not None:
            state.active_platform = str(platform).strip().lower()
        state.last_action = f"open:{str(app_name or '').strip().lower()}" if str(app_name or "").strip() else ""

    def get_app(self) -> str:
        state = self._state()
        if state is None:
            return ""
        return state.get_active_app()

    def set_platform(self, platform: str):
        state = self._state()
        if state is None:
            return
        state.active_platform = str(platform or "").strip().lower()

    def get_platform(self) -> str:
        state = self._state()
        if state is None:
            return ""
        return str(getattr(state, "active_platform", "") or "")

    def reset(self):
        state = self._state()
        if state is None:
            return
        state.active_app = ""
        state.active_platform = "default"
        state.last_action = ""
        state.browser_url = ""


SESSION_CONTEXT = _SessionContextProxy()
