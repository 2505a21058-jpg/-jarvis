"""
rawvision/utils/timeout.py

Hard timeout wrapper for capture layers.
Every layer MUST complete within its timeout.
A hanging layer must never stall the pipeline.

Uses threading.Timer for cross-platform safety.
No asyncio dependency -- capture layers may be sync or async.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import threading
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger("rawvision.utils.timeout")

T = TypeVar("T")

_DEFAULT_TIMEOUT = 5.0
_CAPTURE_TIMEOUT = 3.0
_LAYER_TIMEOUTS = {
    "process_monitor": 5.0,  # was 2.0 - ctypes can be slow first run
    "uia": 8.0,              # was 3.0 - comtypes init takes time
    "cdp": 6.0,              # was 4.0
    "pixel_diff": 4.0,       # was 2.0 - dxcam/mss init slow
    "ocr": 8.0,              # was 5.0
    "screenshot": 5.0,       # was 3.0
}


def run_with_timeout(
    fn: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    default: Any = None,
    layer_name: str = "",
) -> Any:
    """
    Run a synchronous function with a hard timeout.
    Returns default if timeout exceeded or exception raised.
    Never raises -- capture layer failures are logged, not raised.
    """
    effective_timeout = (
        _LAYER_TIMEOUTS.get(layer_name, timeout)
        if layer_name else timeout
    )
    result: dict[str, Any] = {"value": default, "error": None}
    done = threading.Event()
    timed_out = threading.Event()
    cancel_event = threading.Event()
    call_kwargs = dict(kwargs or {})
    cancel_param = _cancel_event_parameter(fn)
    if cancel_param and cancel_param not in call_kwargs:
        call_kwargs[cancel_param] = cancel_event

    def _mark_timeout() -> None:
        timed_out.set()
        cancel_event.set()

    def _target() -> None:
        try:
            result["value"] = fn(*(args or ()), **call_kwargs)
        except Exception as exc:  # pragma: no cover - log path is behavior.
            result["error"] = exc
        finally:
            done.set()

    timer = threading.Timer(effective_timeout, _mark_timeout)
    timer.daemon = True

    thread = threading.Thread(
        target=_target,
        daemon=True,
        name=f"rawvision-timeout-{layer_name or getattr(fn, '__name__', 'fn')}",
    )

    timer.start()
    thread.start()
    finished = done.wait(timeout=effective_timeout)
    timer.cancel()

    if not finished or timed_out.is_set():
        cancel_event.set()
        done.wait(timeout=min(max(float(effective_timeout), 0.1), 1.0))
        logger.warning(
            "[TIMEOUT] Layer '%s' timed out after %.1fs",
            layer_name or "unknown",
            effective_timeout,
        )
        return default

    if result["error"] is not None:
        logger.error(
            "[TIMEOUT] Layer '%s' raised: %s",
            layer_name or "unknown",
            result["error"],
        )
        return default

    return result["value"]


def _cancel_event_parameter(fn: Callable) -> str | None:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return None

    for name in ("cancel_event", "cancellation_event", "timeout_event"):
        param = signature.parameters.get(name)
        if param and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
            return name

    if any(param.kind == param.VAR_KEYWORD for param in signature.parameters.values()):
        return "cancel_event"
    return None


async def run_async_with_timeout(
    coro_fn: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    default: Any = None,
    layer_name: str = "",
) -> Any:
    """
    Run an async coroutine function with a hard timeout.
    Returns default on timeout or exception.
    Never raises.
    """
    effective_timeout = (
        _LAYER_TIMEOUTS.get(layer_name, timeout)
        if layer_name else timeout
    )
    try:
        return await asyncio.wait_for(
            coro_fn(*(args or ()), **(kwargs or {})),
            timeout=effective_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[TIMEOUT] Async layer '%s' timed out after %.1fs",
            layer_name or "unknown",
            effective_timeout,
        )
        return default
    except Exception as exc:
        logger.error(
            "[TIMEOUT] Async layer '%s' raised: %s",
            layer_name or "unknown",
            exc,
        )
        return default


def with_timeout(
    timeout: float = _DEFAULT_TIMEOUT,
    default: Any = None,
    layer_name: str = "",
):
    """
    Decorator: add timeout to any sync function.

    Usage:
        @with_timeout(timeout=3.0, default=[], layer_name="uia")
        def capture_uia_elements():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return run_with_timeout(
                fn,
                args,
                kwargs,
                timeout=timeout,
                default=default,
                layer_name=layer_name or fn.__name__,
            )
        return wrapper
    return decorator


class TimedOperation:
    """
    Context manager that measures elapsed time.
    Used by capture layers to report their timing.

    Usage:
        with TimedOperation("uia_capture") as t:
            elements = capture_uia()
        print(f"Took {t.elapsed_ms:.0f}ms")
    """

    def __init__(self, name: str = ""):
        self.name = name
        self.elapsed_ms = 0.0
        self._start = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.monotonic() - self._start) * 1000
        if self.name:
            logger.debug("[TIMING] %s: %.0fms", self.name, self.elapsed_ms)
