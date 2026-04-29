"""
agent/heartbeat.py

Proactive background awareness loop for Jarvis.
Runs every N minutes, checks memory + state + files.
Fires notifications when high-importance patterns detected.

Notification channels (priority order):
1. System tray notification via plyer (optional)
2. Terminal log output (fallback - always works)

Does NOT block the main agent loop - daemon thread only.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


logger = logging.getLogger("jarvis.heartbeat")

_DEFAULT_INTERVAL_SECONDS = 10 * 60
_DEDUP_WINDOW_SECONDS = 4 * 60 * 60


@dataclass
class HeartbeatSignal:
    title: str
    message: str
    importance: float
    suggested_action: str
    source: str


class HeartbeatLoop:
    def __init__(
        self,
        memory,
        state,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
        notification_callback: Optional[Callable] = None,
    ):
        self._memory = memory
        self._state = state
        self._interval = interval_seconds
        self._notify = notification_callback or self._default_notify
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_signals: dict[str, float] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="jarvis-heartbeat",
            daemon=True,
        )
        self._thread.start()
        logger.info("Heartbeat loop started (interval=%ss)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        self._stop_event.wait(timeout=60.0)
        while not self._stop_event.is_set():
            try:
                signals = self._detect_signals()
                now = time.time()
                for signal in signals:
                    dedup_key = f"{signal.source}:{signal.title}"
                    last_seen = self._last_signals.get(dedup_key, 0.0)
                    if (now - last_seen) >= _DEDUP_WINDOW_SECONDS:
                        self._notify(signal)
                        self._last_signals[dedup_key] = now

                if len(self._last_signals) > 50:
                    cutoff = now - _DEDUP_WINDOW_SECONDS
                    self._last_signals = {
                        key: ts for key, ts in self._last_signals.items() if ts >= cutoff
                    }
            except Exception as exc:
                logger.error("Heartbeat loop error: %s", exc)
            self._stop_event.wait(timeout=self._interval)

    def _detect_signals(self) -> list[HeartbeatSignal]:
        signals: list[HeartbeatSignal] = []
        signals.extend(self._check_memory_patterns())
        signals.extend(self._check_pending_tasks())
        signals.extend(self._check_download_folder())
        return [signal for signal in signals if signal.importance >= 0.6]

    def _check_memory_patterns(self) -> list[HeartbeatSignal]:
        signals: list[HeartbeatSignal] = []
        try:
            recent = self._memory.recent(n=20)
            failed = [
                entry for entry in recent
                if "failed" in str(entry.get("content", "")).lower()
                or "error" in str(entry.get("content", "")).lower()
            ]
            if len(failed) >= 3:
                signals.append(
                    HeartbeatSignal(
                        title="Repeated failures detected",
                        message=f"{len(failed)} recent failures in memory.",
                        importance=0.7,
                        suggested_action="Would you like me to review the recent failures?",
                        source="memory",
                    )
                )

            high_imp = []
            for entry in recent:
                try:
                    data = json.loads(str(entry.get("content", "{}")))
                    if data.get("importance", 0) >= 0.9:
                        high_imp.append(data.get("user_input", ""))
                except Exception:
                    pass
            if high_imp:
                signals.append(
                    HeartbeatSignal(
                        title="Important tasks in memory",
                        message=f"High-priority items: {', '.join(high_imp[:2])}",
                        importance=0.65,
                        suggested_action="Want me to follow up on any of these?",
                        source="memory",
                    )
                )
        except Exception as exc:
            logger.debug("Memory pattern check error: %s", exc)
        return signals

    def _check_pending_tasks(self) -> list[HeartbeatSignal]:
        signals: list[HeartbeatSignal] = []
        try:
            if self._state.task_stack:
                depth = len(self._state.task_stack)
                signals.append(
                    HeartbeatSignal(
                        title=f"{depth} pending tasks in queue",
                        message=f"Tasks waiting: {[t.get('goal', '?') for t in self._state.task_stack[:2]]}",
                        importance=0.75,
                        suggested_action="Shall I continue working on the pending tasks?",
                        source="system",
                    )
                )
        except Exception as exc:
            logger.debug("Task check error: %s", exc)
        return signals

    def _check_download_folder(self) -> list[HeartbeatSignal]:
        signals: list[HeartbeatSignal] = []
        try:
            downloads = os.path.expanduser("~/Downloads")
            if not os.path.exists(downloads):
                return signals

            now = time.time()
            recent_files = [
                fname for fname in os.listdir(downloads)
                if os.path.isfile(os.path.join(downloads, fname))
                and (now - os.path.getmtime(os.path.join(downloads, fname))) < self._interval
            ]

            if recent_files:
                signals.append(
                    HeartbeatSignal(
                        title=f"{len(recent_files)} new file(s) in Downloads",
                        message=f"New: {', '.join(recent_files[:3])}",
                        importance=0.6,
                        suggested_action="Want me to read or organize these files?",
                        source="file",
                    )
                )
        except Exception as exc:
            logger.debug("Downloads check error: %s", exc)
        return signals

    def _default_notify(self, signal: HeartbeatSignal) -> None:
        logger.info(
            "[HEARTBEAT] %s (importance=%s%%)\n  %s\n  -> %s",
            signal.title,
            f"{signal.importance:.0%}".rstrip("%"),
            signal.message,
            signal.suggested_action,
        )
        try:
            from plyer import notification

            notification.notify(
                title=f"Jarvis: {signal.title}",
                message=signal.suggested_action,
                timeout=8,
            )
        except Exception:
            pass
