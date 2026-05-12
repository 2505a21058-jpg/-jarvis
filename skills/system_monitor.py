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


def _get_gpu_info() -> str | None:
    """
    Get GPU information using available methods.
    Tries nvidia-smi first, then WMI on Windows.
    Returns formatted string or None if no GPU info is available.
    """
    import platform
    import subprocess

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = []
            for line in result.stdout.strip().split("\n"):
                parts = [part.strip() for part in line.split(",")]
                if len(parts) < 5:
                    continue
                name, temp, util, mem_used, mem_total = parts[:5]
                try:
                    util_value = float(util)
                except ValueError:
                    util_value = 0.0
                gpu_icon = "[HIGH]" if util_value > 85 else "[WARN]" if util_value > 60 else "[OK]"
                lines.append(
                    f"  {gpu_icon} GPU:    {name}\n"
                    f"           Usage: {util}% | Temp: {temp}C | "
                    f"VRAM: {mem_used}MB / {mem_total}MB"
                )
            if lines:
                return "\n".join(lines)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-WmiObject Win32_VideoController | Select-Object Name,AdapterRAM | Format-List",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                gpu_name = ""
                gpu_ram = ""
                for line in lines:
                    if "Name" in line and ":" in line:
                        gpu_name = line.split(":", 1)[1].strip()
                    if "AdapterRAM" in line and ":" in line:
                        try:
                            ram_bytes = int(line.split(":", 1)[1].strip())
                            gpu_ram = f"{ram_bytes // (1024**3)} GB"
                        except Exception:
                            gpu_ram = "Unknown"
                if gpu_name:
                    return f"  [GPU] GPU:    {gpu_name} ({gpu_ram} VRAM)"
        except Exception:
            pass

    return None


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
            psutil = _get_psutil()
            if not psutil:
                return SkillResult(
                    success=False,
                    output=None,
                    error="psutil not installed. Run: pip install psutil",
                    skill_name=self.name,
                )
            try:
                ram = psutil.virtual_memory()
                cpu = psutil.cpu_percent(interval=0.5)
                disk = psutil.disk_usage("/")
                battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None

                ram_used_gb = ram.used / (1024 ** 3)
                ram_total_gb = ram.total / (1024 ** 3)
                disk_used_gb = disk.used / (1024 ** 3)
                disk_total_gb = disk.total / (1024 ** 3)

                import sys

                supports_emoji = "utf" in (sys.stdout.encoding or "").lower()

                def marker(value: float, warn_at: float, high_at: float) -> str:
                    if supports_emoji:
                        return "🔴" if value > high_at else "🟡" if value > warn_at else "🟢"
                    return "[HIGH]" if value > high_at else "[WARN]" if value > warn_at else "[OK]"

                ram_icon = marker(ram.percent, 65, 85)
                cpu_icon = marker(cpu, 65, 85)
                disk_icon = marker(disk.percent, 75, 90)

                lines = [
                    "System Status:",
                    f"  {ram_icon} RAM:    {ram.percent:.1f}% used  ({ram_used_gb:.1f} GB / {ram_total_gb:.1f} GB)",
                    f"  {cpu_icon} CPU:    {cpu:.1f}%",
                    (
                        f"  {disk_icon} Disk:   {disk.percent:.1f}% used  "
                        f"({disk_used_gb:.1f} GB / {disk_total_gb:.1f} GB free: "
                        f"{(disk_total_gb - disk_used_gb):.1f} GB)"
                    ),
                ]

                if battery:
                    bat_icon = "🔋" if supports_emoji and not battery.power_plugged else (
                        "⚡" if supports_emoji else "[BAT]"
                    )
                    status = "(charging)" if battery.power_plugged else "(on battery)"
                    lines.append(f"  {bat_icon} Battery: {battery.percent:.0f}% {status}")

                gpu_info = _get_gpu_info()
                if gpu_info:
                    lines.append(gpu_info)
                else:
                    lines.append("  [GPU] GPU:    No GPU info available (nvidia-smi not found)")

                import platform

                os_icon = "💻" if supports_emoji else "[OS]"
                lines.append(f"  {os_icon} OS:     {platform.system()} {platform.release()}")

                return SkillResult(success=True, output="\n".join(lines), skill_name=self.name)

            except Exception as exc:
                logger.error("Status check failed: %s", exc)
                return SkillResult(
                    success=False,
                    output=None,
                    error=f"Could not read system stats: {exc}",
                    skill_name=self.name,
                )

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
