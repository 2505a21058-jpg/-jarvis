"""
skills/launch_claude_code.py
Opens Cursor or Claude Code editor, optionally pastes a prompt.
Optional dependency: pyautogui, pyperclip
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import time

from config import EDITOR_COMMAND_PAUSE_SECONDS, EDITOR_LAUNCH_WAIT_SECONDS
from skills.base import SkillBase, SkillResult


logger = logging.getLogger("jarvis.skills.launch_claude_code")

_EDITOR_CANDIDATES = [
    ("cursor", ["cursor"]),
    ("claude-code", ["claude-code"]),
    ("code", ["code"]),
]


def _find_editor():
    for name, cmd in _EDITOR_CANDIDATES:
        if shutil.which(cmd[0]):
            return name, cmd
    return None


class LaunchClaudeCodeSkill(SkillBase):
    name = "launch_claude_code"
    description = "Opens Cursor or Claude Code editor, optionally with a prompt"
    timeout_seconds = 10.0

    def execute(self, params: dict, state) -> SkillResult:
        _ = state
        prompt = str(params.get("prompt", "")).strip()
        project_path = str(params.get("path", ".")).strip()

        editor = _find_editor()
        if not editor:
            return SkillResult(
                success=False,
                output=None,
                error="No compatible editor found. Install Cursor or VS Code.",
            )

        editor_name, cmd = editor
        launch_cmd = cmd + ([project_path] if project_path != "." else [])

        try:
            subprocess.Popen(launch_cmd)
            logger.info("Launched %s at %s", editor_name, project_path)
        except FileNotFoundError:
            return SkillResult(
                success=False,
                output=None,
                error=f"Editor command not found: {cmd[0]}",
            )

        if prompt:
            try:
                # Editor automation waits are named/configurable because app startup speed varies.
                time.sleep(EDITOR_LAUNCH_WAIT_SECONDS)
                import pyautogui

                pyautogui.hotkey("ctrl", "shift", "p")
                time.sleep(EDITOR_COMMAND_PAUSE_SECONDS)
                pyautogui.typewrite("New Chat", interval=0.05)
                time.sleep(EDITOR_COMMAND_PAUSE_SECONDS)
                pyautogui.press("enter")
                time.sleep(EDITOR_COMMAND_PAUSE_SECONDS)

                if platform.system() == "Darwin":
                    import subprocess as sp

                    sp.run(["pbcopy"], input=prompt.encode(), check=False)
                    pyautogui.hotkey("cmd", "v")
                else:
                    import pyperclip

                    pyperclip.copy(prompt)
                    pyautogui.hotkey("ctrl", "v")

                logger.info("Pasted prompt into %s", editor_name)
            except ImportError:
                logger.warning("pyautogui not available - editor opened without prompt paste")
            except Exception as exc:
                logger.warning("Prompt paste failed (non-critical): %s", exc)

        output = f"Opened {editor_name}"
        if prompt:
            output += f" with prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}"
        return SkillResult(success=True, output=output)
