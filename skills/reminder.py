"""
skills/reminder.py

Sets real timers that fire user notifications after a delay.
Uses threading.Timer - no blocking, no external dependencies.

Params:
  message: str - what to remind about
  delay_seconds: float - when to fire
  delay_minutes: float - alternative to delay_seconds
"""

import logging
import threading

from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.reminder")

# Active reminders: {reminder_id: Timer}
_active_reminders: dict[str, threading.Timer] = {}
_reminder_counter = 0


def _fire_reminder(reminder_id: str, message: str) -> None:
    """Called when timer expires."""
    _active_reminders.pop(reminder_id, None)
    logger.info("Reminder fired: %s", message)

    # Terminal notification always works, even without optional desktop packages.
    print(f"\nJARVIS REMINDER: {message}\n")

    try:
        from plyer import notification

        notification.notify(title="Jarvis Reminder", message=message, timeout=15)
    except Exception:
        pass


def _parse_delay(params: dict) -> float:
    """
    Parse delay from params dict.
    Accepts: delay_seconds, delay_minutes, delay_hours, or natural text in 'delay'.
    Returns delay in seconds.
    """
    if "delay_seconds" in params:
        return float(params["delay_seconds"])
    if "delay_minutes" in params:
        return float(params["delay_minutes"]) * 60
    if "delay_hours" in params:
        return float(params["delay_hours"]) * 3600

    delay_text = str(params.get("delay", "1")).lower().strip()
    try:
        # Pure number = minutes by default.
        return float(delay_text) * 60
    except ValueError:
        pass

    import re

    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(?:second|seconds|sec|secs|s)\b", 1),
        (r"(\d+(?:\.\d+)?)\s*(?:minute|minutes|min|mins|m)\b", 60),
        (r"(\d+(?:\.\d+)?)\s*(?:hour|hours|hr|hrs|h)\b", 3600),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, delay_text)
        if match:
            return float(match.group(1)) * multiplier

    return 60.0


class ReminderSkill(SkillBase):
    name = "reminder"
    description = "Sets a timed reminder that fires a notification after a delay"
    timeout_seconds = 2.0

    def execute(self, params: dict, state) -> SkillResult:
        global _reminder_counter

        message = params.get("message", "").strip()
        if not message:
            message = params.get("task", params.get("about", "Check in"))

        if not message:
            return SkillResult(
                success=False,
                output=None,
                error="No reminder message provided. Say 'remind me in 5 minutes to check my code'",
                skill_name=self.name,
            )

        delay_seconds = _parse_delay(params)

        if delay_seconds <= 0:
            return SkillResult(
                success=False,
                output=None,
                error="Delay must be greater than 0.",
                skill_name=self.name,
            )

        if delay_seconds > 24 * 3600:
            return SkillResult(
                success=False,
                output=None,
                error="Maximum reminder delay is 24 hours.",
                skill_name=self.name,
            )

        _reminder_counter += 1
        reminder_id = f"reminder_{_reminder_counter}"

        timer = threading.Timer(
            interval=delay_seconds,
            function=_fire_reminder,
            args=(reminder_id, message),
        )
        timer.daemon = True
        timer.start()
        _active_reminders[reminder_id] = timer

        if delay_seconds < 60:
            time_str = f"{int(delay_seconds)} second(s)"
        elif delay_seconds < 3600:
            time_str = f"{delay_seconds / 60:.0f} minute(s)"
        else:
            time_str = f"{delay_seconds / 3600:.1f} hour(s)"

        logger.info("Reminder set: '%s' in %s", message, time_str)
        return SkillResult(
            success=True,
            output=f"Reminder set: I'll remind you to '{message}' in {time_str}.",
            skill_name=self.name,
        )
