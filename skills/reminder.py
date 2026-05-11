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
import datetime
import re
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


def _parse_time_string(time_str: str) -> float | None:
    """
    Parse an absolute clock time string and return seconds until that time.
    Examples: "10 o clock", "9:06 am", "10 PM", "14:30"
    Returns None if not a clock time string.
    """
    time_str = time_str.strip().lower()
    time_str = re.sub(r"o.?clock", "", time_str).strip()

    formats_to_try = [
        "%I:%M %p",
        "%I %p",
        "%H:%M",
        "%H",
        "%I:%M%p",
        "%I%p",
    ]

    now = datetime.datetime.now()
    parsed_time = None

    for fmt in formats_to_try:
        try:
            parsed_time = datetime.datetime.strptime(time_str, fmt)
            break
        except ValueError:
            continue

    if parsed_time is None:
        return None

    target = now.replace(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        second=0,
        microsecond=0,
    )

    if target <= now:
        target += datetime.timedelta(days=1)

    return (target - now).total_seconds()


def _parse_delay(params: dict) -> float:
    """
    Parse delay from params dict.
    Handles both relative ("5 minutes") and absolute ("10 o clock") time.
    Returns delay in seconds.
    """
    if "delay_seconds" in params:
        return float(params["delay_seconds"])
    if "delay_minutes" in params:
        return float(params["delay_minutes"]) * 60
    if "delay_hours" in params:
        return float(params["delay_hours"]) * 3600

    delay_text = str(params.get("delay", "5 minutes")).strip()

    clock_seconds = _parse_time_string(delay_text)
    if clock_seconds is not None:
        return clock_seconds

    try:
        return float(delay_text) * 60
    except ValueError:
        pass

    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b", 1),
        (r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m)\b", 60),
        (r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", 3600),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, delay_text, re.IGNORECASE)
        if match:
            return float(match.group(1)) * multiplier

    return 300.0


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

        fire_time = datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)
        fire_time_str = fire_time.strftime("%I:%M %p")

        if delay_seconds < 60:
            delay_display = f"{int(delay_seconds)} second(s)"
        elif delay_seconds < 3600:
            delay_display = f"{delay_seconds / 60:.0f} minute(s)"
        else:
            delay_display = f"{delay_seconds / 3600:.1f} hour(s)"

        is_alarm = params.get("is_alarm", False)
        label = "Alarm" if is_alarm else "Reminder"

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

        logger.info("%s set: '%s' for %s", label, message, fire_time_str)
        return SkillResult(
            success=True,
            output=(
                f"✓ {label} set for {fire_time_str} "
                f"(in {delay_display}).\n"
                f"Message: '{message}'"
            ),
            skill_name=self.name,
        )
