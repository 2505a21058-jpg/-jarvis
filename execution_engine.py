import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Mapping, Sequence

DEBUG = False


@dataclass
class CommandResult:
    success: bool
    output: str = ""
    stderr: str = ""
    error: str = ""
    return_code: int = 0
    command: str = ""
    pid: int | None = None
    stdout: str = ""

    def __post_init__(self):
        self.command = str(self.command or "")
        self.output = _clean_process_output(self.output)
        self.stderr = _clean_process_output(self.stderr)
        self.error = _clean_process_output(self.error)
        self.stdout = _clean_process_output(self.stdout or self.output)
        self.return_code = int(self.return_code) if isinstance(self.return_code, (int, bool)) else 0

    @property
    def ok(self) -> bool:
        return self.success

    @property
    def returncode(self) -> int:
        return self.return_code


def _command_label(command: Sequence[str] | str) -> str:
    if isinstance(command, str):
        return command
    return " ".join(str(part) for part in command)


def _debug_log(message: str):
    if DEBUG:
        print(f"[Exec] {message}")


def _clean_process_output(value) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _timeout_result(command_label: str, exc: subprocess.TimeoutExpired) -> CommandResult:
    stdout = _clean_process_output(exc.stdout)
    stderr = _clean_process_output(exc.stderr)
    return CommandResult(
        success=False,
        output=stdout,
        stderr=stderr,
        error="Command timed out",
        return_code=124,
        command=command_label,
    )


def run_system_command(
    command: Sequence[str] | str,
    *,
    timeout: int = 10,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    capture_output: bool = True,
) -> CommandResult:
    command_label = _command_label(command)
    started_at = time.perf_counter()
    _debug_log(f"run: {command_label}")

    try:
        completed = subprocess.run(
            command,
            shell=False,
            cwd=cwd,
            env=dict(env) if env else None,
            timeout=timeout,
            text=True,
            capture_output=capture_output,
        )
        result = CommandResult(
            success=(completed.returncode == 0),
            output=_clean_process_output(completed.stdout),
            stderr=_clean_process_output(completed.stderr),
            error="" if completed.returncode == 0 else _clean_process_output(completed.stderr),
            return_code=completed.returncode,
            command=command_label,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"{'success' if result.success else 'failure'}: {command_label} ({elapsed_ms:.1f} ms)")
        return result
    except FileNotFoundError as exc:
        result = CommandResult(success=False, error=str(exc), return_code=1, command=command_label)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"failure: {command_label} ({elapsed_ms:.1f} ms)")
        return result
    except subprocess.TimeoutExpired as exc:
        result = _timeout_result(command_label, exc)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"failure: {command_label} ({elapsed_ms:.1f} ms)")
        return result
    except Exception as exc:
        result = CommandResult(success=False, error=str(exc), return_code=1, command=command_label)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"failure: {command_label} ({elapsed_ms:.1f} ms)")
        return result


def run_shell_command(
    command: str,
    *,
    timeout: int = 10,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    capture_output: bool = True,
) -> CommandResult:
    started_at = time.perf_counter()
    _debug_log(f"run: {command}")
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env=dict(env) if env else None,
            timeout=timeout,
            text=True,
            capture_output=capture_output,
        )
        result = CommandResult(
            success=(completed.returncode == 0),
            output=_clean_process_output(completed.stdout),
            stderr=_clean_process_output(completed.stderr),
            error="" if completed.returncode == 0 else _clean_process_output(completed.stderr),
            return_code=completed.returncode,
            command=command,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"{'success' if result.success else 'failure'}: {command} ({elapsed_ms:.1f} ms)")
        return result
    except subprocess.TimeoutExpired as exc:
        result = _timeout_result(command, exc)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"failure: {command} ({elapsed_ms:.1f} ms)")
        return result
    except Exception as exc:
        result = CommandResult(success=False, error=str(exc), return_code=1, command=command)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"failure: {command} ({elapsed_ms:.1f} ms)")
        return result


def run_python_code(
    code: str,
    *,
    timeout: int = 10,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    return run_system_command(
        [sys.executable, "-c", code],
        timeout=timeout,
        cwd=cwd,
        env=env,
        capture_output=True,
    )


def launch_system_command(
    command: Sequence[str] | str,
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    shell: bool = False,
) -> CommandResult:
    command_label = _command_label(command)
    started_at = time.perf_counter()
    _debug_log(f"launch: {command_label}")

    try:
        process = subprocess.Popen(
            command,
            shell=shell,
            cwd=cwd,
            env=dict(env) if env else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result = CommandResult(success=True, command=command_label, pid=process.pid)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"success: {command_label} ({elapsed_ms:.1f} ms)")
        return result
    except FileNotFoundError as exc:
        result = CommandResult(success=False, error=str(exc), return_code=1, command=command_label)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"failure: {command_label} ({elapsed_ms:.1f} ms)")
        return result
    except Exception as exc:
        result = CommandResult(success=False, error=str(exc), return_code=1, command=command_label)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        _debug_log(f"failure: {command_label} ({elapsed_ms:.1f} ms)")
        return result


def launch_python_file(
    path: str,
    *,
    args: Sequence[str] | None = None,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    command = [sys.executable, path, *(list(args) if args else [])]
    return launch_system_command(command, cwd=cwd, env=env, shell=False)


def command_exists(path: str) -> bool:
    return bool(path) and os.path.exists(path)
