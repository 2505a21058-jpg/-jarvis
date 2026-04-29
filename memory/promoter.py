"""
memory/promoter.py
Background promotion scheduler. Runs as a daemon thread.
"""

import logging
import threading


logger = logging.getLogger("jarvis.memory.promoter")

_SWEEP_INTERVAL_SECONDS = 8 * 60 * 60


class PromotionScheduler:
    def __init__(self, memory, min_importance: float = 0.8):
        self._memory = memory
        self._min_importance = min_importance
        self._thread = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="jarvis-promoter",
            daemon=True,
        )
        self._thread.start()
        logger.info("PromotionScheduler started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def run_now(self) -> int:
        return self._memory.run_promotion_sweep(self._min_importance)

    def _run(self) -> None:
        self._stop_event.wait(timeout=_SWEEP_INTERVAL_SECONDS)
        while not self._stop_event.is_set():
            try:
                count = self._memory.run_promotion_sweep(self._min_importance)
                logger.info("Scheduled sweep: %s entries promoted", count)
            except Exception as exc:
                logger.error("Promotion sweep error: %s", exc)
            self._stop_event.wait(timeout=_SWEEP_INTERVAL_SECONDS)
