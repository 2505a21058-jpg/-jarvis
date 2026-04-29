"""
skills/timeout_utils.py
Cross-platform timeout utility. Uses SIGALRM on Unix, threading.Timer on Windows.
"""

from __future__ import annotations

import logging
import platform
import threading
from typing import Any, Callable


logger = logging.getLogger("jarvis.skills.timeout")

_IS_UNIX = platform.system() != "Windows"


class TimeoutError(Exception):
    pass


def run_with_timeout(
    fn: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    timeout_seconds: float = 15.0,
) -> Any:
    kwargs = kwargs or {}
    if _IS_UNIX and threading.current_thread() is threading.main_thread():
        return _run_with_signal(fn, args, kwargs, timeout_seconds)
    return _run_with_thread(fn, args, kwargs, timeout_seconds)


def _run_with_signal(fn, args, kwargs, timeout_seconds):
    import signal

    def _handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {timeout_seconds}s")

    original = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(int(timeout_seconds))
    try:
        result = fn(*args, **kwargs)
        signal.alarm(0)
        return result
    except TimeoutError:
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original)


def _run_with_thread(fn, args, kwargs, timeout_seconds):
    result_container = [None]
    exception_container = [None]
    done_event = threading.Event()

    def _target():
        try:
            result_container[0] = fn(*args, **kwargs)
        except Exception as exc:
            exception_container[0] = exc
        finally:
            done_event.set()

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    finished = done_event.wait(timeout=timeout_seconds)

    if not finished:
        raise TimeoutError(f"Operation timed out after {timeout_seconds}s")
    if exception_container[0]:
        raise exception_container[0]
    return result_container[0]
