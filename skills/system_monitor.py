"""
skills/system_monitor.py

Real-time system monitoring skill.
Uses psutil for cross-platform CPU, RAM, disk stats.
Optional dependency: pip install psutil

Monitors in a background thread and fires a notification
via the heartbeat notification channel when thresholds are exceeded.
"""

import logging
import threading
import time

from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.system_monitor")

# Active monitors: {monitor_id: MonitorThread}
_active_monitors: dict[str, threading.Thread] = {}
_monitor_stop_events: dict[str, threading.Event] = {}

_VALID_METRICS = {"ram", "cpu", "disk"}


def _get_psutil():
    try:
        import psutil

        return psutil
    except ImportError:
        return None


def _notify_user(message: str) -> None:
    """Send notification via available channel."""
    logger.info("[MONITOR ALERT] %s", message)
    try:
        from plyer import notification

        notification.notify(title="Jarvis Monitor Alert", message=message, timeout=10)
    except Exception:
        pass

    # Terminal fallback is intentionally kept even if desktop notifications fail.
    print(f"\nJARVIS ALERT: {message}\n")


def _monitor_thread(
    monitor_id: str,
    metric: str,
    threshold: float,
    stop_event: threading.Event,
    check_interval: float = 30.0,
) -> None:
    """Background thread that monitors a system metric."""
    psutil = _get_psutil()
    if not psutil:
        logger.error("psutil not installed - cannot monitor system")
        return

    alert_cooldown = 5 * 60
    last_alert_time = 0.0

    while not stop_event.is_set():
        try:
            current_value = None

            if metric == "ram":
                current_value = psutil.virtual_memory().percent
            elif metric == "cpu":
                current_value = psutil.cpu_percent(interval=1)
            elif metric == "disk":
                current_value = psutil.disk_usage("/").percent

            if current_value is not None and current_value > threshold:
                now = time.time()
                if now - last_alert_time > alert_cooldown:
                    _notify_user(
                        f"{metric.upper()} usage is {current_value:.1f}% "
                        f"(above your {threshold}% threshold)"
                    )
                    last_alert_time = now
        except Exception as exc:
            logger.debug("Monitor thread error for %s: %s", monitor_id, exc)

        stop_event.wait(timeout=check_interval)


class SystemMonitorSkill(SkillBase):
    name = "system_monitor"
    description = "Monitors CPU, RAM, or disk usage and alerts when thresholds are exceeded"
    timeout_seconds = 5.0

    def execute(self, params: dict, state) -> SkillResult:
        psutil = _get_psutil()
        if not psutil:
            return SkillResult(
                success=False,
                output=None,
                error="psutil not installed. Run: pip install psutil",
            )

        action = params.get("action", "status").lower()

        if action == "status":
            ram = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            disk = psutil.disk_usage("/")
            output = (
                "System Status:\n"
                f"  RAM: {ram.percent:.1f}% used ({ram.used / (1024**3):.1f}GB / {ram.total / (1024**3):.1f}GB)\n"
                f"  CPU: {cpu:.1f}%\n"
                f"  Disk: {disk.percent:.1f}% used"
            )
            return SkillResult(success=True, output=output, skill_name=self.name)

        if action == "monitor":
            metric = params.get("metric", "ram").lower()
            threshold = float(params.get("threshold", 80.0))

            if metric == "memory":
                metric = "ram"
            if metric not in _VALID_METRICS:
                return SkillResult(
                    success=False,
                    output=None,
                    error=f"Unknown metric '{metric}'. Use: ram, cpu, disk",
                    skill_name=self.name,
                )

            monitor_id = f"{metric}_{threshold:g}"
            if monitor_id in _active_monitors:
                return SkillResult(
                    success=True,
                    output=f"Already monitoring {metric.upper()} (threshold: {threshold:g}%)",
                    skill_name=self.name,
                )

            stop_event = threading.Event()
            _monitor_stop_events[monitor_id] = stop_event

            thread = threading.Thread(
                target=_monitor_thread,
                args=(monitor_id, metric, threshold, stop_event),
                daemon=True,
                name=f"jarvis-monitor-{monitor_id}",
            )
            _active_monitors[monitor_id] = thread
            thread.start()

            return SkillResult(
                success=True,
                output=(
                    f"Now monitoring {metric.upper()}. "
                    f"You'll be alerted if it exceeds {threshold:g}%. "
                    f"Say 'stop monitoring {metric}' to cancel."
                ),
                skill_name=self.name,
            )

        if action == "stop":
            metric = params.get("metric", "ram").lower()
            if metric == "memory":
                metric = "ram"

            stopped = []
            for monitor_id, stop_event in list(_monitor_stop_events.items()):
                if metric in monitor_id or metric == "all":
                    stop_event.set()
                    del _monitor_stop_events[monitor_id]
                    _active_monitors.pop(monitor_id, None)
                    stopped.append(monitor_id)

            if stopped:
                return SkillResult(
                    success=True,
                    output=f"Stopped monitoring: {', '.join(stopped)}",
                    skill_name=self.name,
                )
            return SkillResult(
                success=True,
                output=f"No active {metric} monitor found.",
                skill_name=self.name,
            )

        return SkillResult(
            success=False,
            output=None,
            error=f"Unknown action '{action}'. Use: status, monitor, stop",
            skill_name=self.name,
        )
