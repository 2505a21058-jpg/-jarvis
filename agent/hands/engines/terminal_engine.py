"""
agent/hands/engines/terminal_engine.py

Terminal engine - direct command execution via ConPTY/subprocess.
100% reliable for CMD, PowerShell, terminal apps.
No keyboard simulation needed.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import signal
import subprocess
from typing import Optional

from agent.hands.engines.base import ActionResult, fail, ok
from permissions.policy import PolicyEngine

logger = logging.getLogger("jarvis.hands.terminal")


_DENIED_COMMAND_PATTERNS = (
    "rm -rf",
    "del /f",
    "format ",
    "shutdown",
    "restart",
    "remove-item -recurse",
    "rmdir /s",
    "rd /s",
    "reg delete",
    "diskpart",
    "bcdedit",
    "mkfs",
    "dd if=",
    "cipher /w",
)


@dataclass(frozen=True)
class _ProcessResult:
    success: bool
    output: str
    returncode: int
    timed_out: bool = False


class TerminalEngine:
    """Direct terminal control via subprocess/ConPTY."""

    name = "terminal"

    def __init__(self, policy_engine: PolicyEngine | None = None, require_approval: bool = True):
        self._policy_engine = policy_engine or PolicyEngine.instance()
        self.require_approval = bool(require_approval)

    def run(self, command: str, timeout: float = 30, *, approved: bool = False) -> tuple[bool, str]:
        """Execute command and return (success, output)."""
        allowed, reason = self._check_permission(
            "terminal_command",
            {"command": command},
            approved=approved,
        )
        if not allowed:
            logger.warning("[TERMINAL] Command denied: %s", reason)
            return False, reason

        try:
            result = self._run_process(
                command,
                shell=True,
                timeout=timeout,
                label=command,
            )
            logger.info(
                "[TERMINAL] Ran: %s | exit=%s | out=%d chars",
                command[:60],
                result.returncode,
                len(result.output),
            )
            if result.timed_out:
                return False, "Command timed out"
            return result.success, result.output.strip()
        except Exception as e:
            logger.error("[TERMINAL] Run failed: %s", e)
            return False, str(e)

    def run_powershell(self, script: str, timeout: float = 30, *, approved: bool = False) -> tuple[bool, str]:
        """Run PowerShell script."""
        allowed, reason = self._check_permission(
            "terminal_powershell",
            {"script": script},
            approved=approved,
        )
        if not allowed:
            logger.warning("[TERMINAL] PowerShell denied: %s", reason)
            return False, reason

        try:
            result = self._run_process(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                timeout=timeout,
                label=script,
            )
            if result.timed_out:
                return False, "PowerShell command timed out"
            return result.success, result.output.strip()
        except Exception as e:
            logger.error("[TERMINAL] PowerShell failed: %s", e)
            return False, str(e)

    def run_background(self, command: str, *, approved: bool = False) -> subprocess.Popen:
        """Launch process in background."""
        allowed, reason = self._check_permission(
            "terminal_background",
            {"command": command},
            approved=approved,
        )
        if not allowed:
            raise PermissionError(reason)
        return subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creationflags(),
            start_new_session=os.name != "nt",
        )

    def run_command(self, command: str, timeout: float = 10.0, *, approved: bool = False) -> ActionResult:
        """Compatibility wrapper returning ActionResult."""
        success, output = self.run(command, timeout=float(timeout), approved=approved)
        data = {"stdout": output if success else "", "stderr": "" if success else output}
        return (
            ok(self.name, "command completed", returncode=0, **data)
            if success
            else fail(self.name, output or "command failed", returncode=1, **data)
        )

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

    def _check_permission(self, skill_name: str, params: dict, *, approved: bool) -> tuple[bool, str]:
        text = " ".join(str(value or "") for value in params.values()).strip()
        lowered = text.lower()
        for pattern in _DENIED_COMMAND_PATTERNS:
            if pattern in lowered:
                return False, f"Terminal command denied by policy pattern: '{pattern}'"

        policy_result = self._policy_engine.check(skill_name, params, user_input=text)
        if not policy_result.allowed:
            return False, policy_result.reason or f"{skill_name} denied by policy"

        if policy_result.require_confirmation and not approved:
            return False, policy_result.reason or "Terminal command requires approval"

        if self.require_approval and not approved:
            return False, "Terminal command requires approval"

        return True, ""

    def _run_process(self, command, *, shell: bool = False, timeout: float, label: str) -> _ProcessResult:
        process = subprocess.Popen(
            command,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creationflags(),
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = process.communicate(timeout=max(float(timeout), 0.1))
            output = (stdout or "") + (stderr or "")
            return _ProcessResult(process.returncode == 0, output, int(process.returncode or 0))
        except subprocess.TimeoutExpired:
            logger.warning("[TERMINAL] Command timed out, terminating process tree: %s", label[:60])
            _terminate_process_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            output = (stdout or "") + (stderr or "")
            return _ProcessResult(False, output, int(process.returncode or 1), timed_out=True)


def _creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
            return
        except Exception as exc:
            logger.debug("[TERMINAL] taskkill failed for pid=%s: %s", process.pid, exc)

    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=1.0)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
        except Exception as exc:
            logger.debug("[TERMINAL] process kill failed for pid=%s: %s", process.pid, exc)
