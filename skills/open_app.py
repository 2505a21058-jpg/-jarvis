"""
skills/open_app.py

Opens system applications or web services by name.
- Known apps: launched via subprocess from APP_MAP
- Web services (gmail, youtube, etc.): opened via browser URL
- Unknown apps: attempted via subprocess with shutil.which() discovery
- Windows: also tries Start Menu search via PowerShell as last resort
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from typing import Any

from skills.base import SkillBase, SkillResult


logger = logging.getLogger("jarvis.skills.open_app")

WEB_APPS = {
    "gmail": "https://mail.google.com",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "twitter": "https://www.twitter.com",
    "x": "https://www.x.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "linkedin": "https://www.linkedin.com",
    "github": "https://www.github.com",
    "reddit": "https://www.reddit.com",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "outlook": "https://outlook.live.com",
    "hotmail": "https://outlook.live.com",
    "drive": "https://drive.google.com",
    "docs": "https://docs.google.com",
    "sheets": "https://sheets.google.com",
    "calendar": "https://calendar.google.com",
    "meet": "https://meet.google.com",
    "zoom": "https://zoom.us",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "notion": "https://www.notion.so",
    "trello": "https://trello.com",
    "email": "https://mail.google.com",
    "mail": "https://mail.google.com",
}

_IS_WINDOWS = platform.system() == "Windows"
_IS_MAC = platform.system() == "Darwin"

APP_MAP_WINDOWS = {
    "chrome": [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "chrome.exe",
    ],
    "firefox": [
        "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
        "C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe",
        "firefox.exe",
    ],
    "edge": ["msedge.exe"],
    "notepad": ["notepad.exe"],
    "notepad++": ["notepad++.exe"],
    "calculator": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "wordpad": ["wordpad.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "folder": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "terminal": ["wt.exe"],
    "vscode": ["code"],
    "vs code": ["code"],
    "code": ["code"],
    "cursor": ["cursor"],
    "word": ["winword.exe"],
    "excel": ["excel.exe"],
    "powerpoint": ["powerpnt.exe"],
    "outlook": ["outlook.exe"],
    "teams": ["teams.exe"],
    "discord": ["discord.exe"],
    "slack": ["slack.exe"],
    "spotify": ["spotify.exe"],
    "steam": ["steam.exe"],
    "vlc": ["vlc.exe"],
    "obs": ["obs64"],
    "photoshop": ["photoshop"],
    "task manager": ["taskmgr.exe"],
    "settings": ["ms-settings:"],
    "control panel": ["control"],
    "chatgpt": ["chatgpt.exe"],
    "claude": ["claude.exe"],
}

APP_MAP_MAC = {
    "chrome": ["open", "-a", "Google Chrome"],
    "firefox": ["open", "-a", "Firefox"],
    "safari": ["open", "-a", "Safari"],
    "terminal": ["open", "-a", "Terminal"],
    "vscode": ["open", "-a", "Visual Studio Code"],
    "vs code": ["open", "-a", "Visual Studio Code"],
    "code": ["open", "-a", "Visual Studio Code"],
    "cursor": ["open", "-a", "Cursor"],
    "notes": ["open", "-a", "Notes"],
    "finder": ["open", "-a", "Finder"],
    "calculator": ["open", "-a", "Calculator"],
    "discord": ["open", "-a", "Discord"],
    "slack": ["open", "-a", "Slack"],
    "word": ["open", "-a", "Microsoft Word"],
    "excel": ["open", "-a", "Microsoft Excel"],
    "powerpoint": ["open", "-a", "Microsoft PowerPoint"],
    "spotify": ["open", "-a", "Spotify"],
    "chatgpt": ["open", "-a", "ChatGPT"],
    "claude": ["open", "-a", "Claude"],
}

APP_MAP_LINUX = {
    "chrome": ["google-chrome"],
    "firefox": ["firefox"],
    "terminal": ["gnome-terminal"],
    "vscode": ["code"],
    "vs code": ["code"],
    "code": ["code"],
    "cursor": ["cursor"],
    "calculator": ["gnome-calculator"],
    "files": ["nautilus"],
    "folder": ["nautilus"],
    "spotify": ["spotify"],
    "discord": ["discord"],
    "slack": ["slack"],
    "gedit": ["gedit"],
    "notes": ["gedit"],
}

ALIASES = {
    "browser": "chrome",
    "note": "notepad",
    "calc": "calculator",
    "file explorer": "explorer",
}


def _tool_result(success: bool, output=None, error: str | None = None):
    return {
        "success": bool(success),
        "output": output,
        "error": error,
    }


def _get_app_map() -> dict[str, list[str]]:
    if _IS_WINDOWS:
        return APP_MAP_WINDOWS
    if _IS_MAC:
        return APP_MAP_MAC
    return APP_MAP_LINUX


_MAX_APP_NAME_WORDS = 3
_MAX_APP_NAME_CHARS = 30


def _iter_command_options(cmd_options: list[str] | list[list[str]]) -> list[list[str]]:
    if not isinstance(cmd_options, list):
        return [[str(cmd_options)]]
    if not cmd_options:
        return []
    if all(isinstance(item, list) for item in cmd_options):
        return [list(item) for item in cmd_options]
    if _IS_WINDOWS:
        return [[str(item)] for item in cmd_options]
    return [[str(item) for item in cmd_options]]


def _try_windows_start(app_name: str) -> bool:
    """
    Last resort: use Windows Start Menu to launch an app.
    Only attempts if app_name looks like a real app name.
    Rejects multi-word compound sentences.
    """
    word_count = len(app_name.split())
    if word_count > _MAX_APP_NAME_WORDS:
        logger.debug("Skipping Start Menu for multi-word input: '%s'", app_name)
        return False

    if len(app_name) > _MAX_APP_NAME_CHARS:
        logger.debug("Skipping Start Menu for long input: '%s'", app_name)
        return False

    reject_words = {"and", "then", "for", "with", "to", "from", "in", "on", "at"}
    words = set(app_name.lower().split())
    if words & reject_words:
        logger.debug("Skipping Start Menu - contains connector words: '%s'", app_name)
        return False

    try:
        subprocess.Popen(
            ["powershell", "-Command", f"Start-Process '{app_name}'"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Launched '%s' via Windows Start Menu", app_name)
        return True
    except Exception as exc:
        logger.debug("Start Menu launch failed: %s", exc)
        return False


def _set_state(state: Any, app_name: str, browser_url: str | None = None) -> None:
    if state is None:
        return
    if hasattr(state, "set_active_app"):
        state.set_active_app(app_name)
    elif hasattr(state, "active_app"):
        state.active_app = app_name
    elif isinstance(state, dict):
        state["active_app"] = app_name

    if browser_url:
        if hasattr(state, "browser_url"):
            state.browser_url = browser_url
        elif isinstance(state, dict):
            state["browser_url"] = browser_url


class OpenAppSkill(SkillBase):
    name = "open_app"
    description = "Opens a desktop application or web service by name"
    timeout_seconds = 8.0

    def execute(self, params: dict, state) -> SkillResult:
        app_name = str(params.get("app") or params.get("target") or "").strip().lower()
        app_name = ALIASES.get(app_name, app_name)

        if not app_name:
            return SkillResult(
                success=False,
                output=None,
                error="No app name provided. Say 'open chrome' or 'open gmail'.",
            )

        if app_name in WEB_APPS:
            url = WEB_APPS[app_name]
            try:
                import webbrowser

                webbrowser.open(url)
                _set_state(state, "browser", browser_url=url)
                logger.info("Opened web service '%s' at %s", app_name, url)
                return SkillResult(success=True, output=f"Opened {app_name} in browser")
            except Exception as exc:
                return SkillResult(success=False, output=None, error=str(exc))

        app_map = _get_app_map()
        cmd_options = app_map.get(app_name)

        if cmd_options:
            for cmd in _iter_command_options(cmd_options):
                try:
                    subprocess.Popen(cmd, shell=False)
                    _set_state(state, app_name)
                    logger.info("Opened app '%s' via APP_MAP: %s", app_name, cmd)
                    return SkillResult(success=True, output=f"Opened {app_name}")
                except (FileNotFoundError, OSError):
                    logger.debug("Path failed for '%s': %s", app_name, cmd)
                    continue
                except Exception as exc:
                    logger.warning("APP_MAP execution failed for '%s': %s", app_name, exc)
                    continue
            logger.warning("All APP_MAP paths failed for '%s'", app_name)

        executable = shutil.which(app_name)
        if executable:
            try:
                subprocess.Popen([executable])
                _set_state(state, app_name)
                logger.info("Opened '%s' via PATH discovery", app_name)
                return SkillResult(success=True, output=f"Opened {app_name}")
            except Exception as exc:
                logger.warning("PATH execution failed for '%s': %s", app_name, exc)

        if _IS_WINDOWS and _try_windows_start(app_name):
            _set_state(state, app_name)
            logger.info("Opened '%s' via Windows Start Menu", app_name)
            return SkillResult(success=True, output=f"Opened {app_name}")

        suggestion = f"Try 'go to {app_name}.com' if it's a website."
        logger.warning("App not found: '%s'", app_name)
        return SkillResult(
            success=False,
            output=None,
            error=(
                f"Could not find '{app_name}' on this system. "
                f"Available apps include: {', '.join(list(app_map.keys())[:8])}... "
                f"{suggestion}"
            ),
        )


def open_app(app_name: str, url: str | None = None, state: Any = None) -> dict[str, Any]:
    params = {"app": app_name}
    if url:
        params["url"] = url
    result = OpenAppSkill().run(params, state or {})
    return _tool_result(result.success, result.output, result.error)
