"""
agent/hands/engines/terminal_engine.py

Terminal engine - direct command execution via ConPTY/subprocess.
100% reliable for CMD, PowerShell, terminal apps.
No keyboard simulation needed.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from agent.hands.engines.base import ActionResult, fail, ok

logger = logging.getLogger("jarvis.hands.terminal")


class TerminalEngine:
    """Direct terminal control via subprocess/ConPTY."""

    name = "terminal"

    def run(self, command: str, timeout: int = 30) -> tuple[bool, str]:
        """Execute command and return (success, output)."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout + result.stderr
            logger.info(
                "[TERMINAL] Ran: %s | exit=%s | out=%d chars",
                command[:60],
                result.returncode,
                len(output),
            )
            return result.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            logger.warning("[TERMINAL] Command timed out: %s", command[:60])
            return False, "Command timed out"
        except Exception as e:
            logger.error("[TERMINAL] Run failed: %s", e)
            return False, str(e)

    def run_powershell(self, script: str, timeout: int = 30) -> tuple[bool, str]:
        """Run PowerShell script."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode == 0, (result.stdout + result.stderr).strip()
        except Exception as e:
            logger.error("[TERMINAL] PowerShell failed: %s", e)
            return False, str(e)

    def run_background(self, command: str) -> subprocess.Popen:
        """Launch process in background."""
        return subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def run_command(self, command: str, timeout: float = 10.0) -> ActionResult:
        """Compatibility wrapper returning ActionResult."""
        success, output = self.run(command, timeout=int(timeout))
        data = {"stdout": output if success else "", "stderr": "" if success else output}
        return ok(self.name, "command completed", returncode=0, **data) if success else fail(self.name, "command failed", returncode=1, **data)

    def type_text(self, text: str, process: Optional[subprocess.Popen] = None) -> ActionResult:
        if process is None or process.stdin is None:
            return fail(self.name, "no terminal stdin")
        try:
            process.stdin.write(text)
            process.stdin.flush()
            return ok(self.name, "typed")
        except Exception as exc:
            return fail(self.name, str(exc))

    def press_enter(self, process: Optional[subprocess.Popen] = None) -> ActionResult:
        return self.type_text("\n", process=process)
