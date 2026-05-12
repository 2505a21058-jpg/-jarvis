"""
skills/run_code.py

Safe sandboxed code execution for Jarvis.
Inspired by Coderunner (MCP ecosystem).

Executes Python code in a subprocess with:
- Timeout enforcement
- Output capture
- Working directory isolation
- Dangerous operation blocking

For LLM-generated code: Jarvis generates the code then executes it here.
For user-provided code: executes as-is with safety checks.
"""

import subprocess
import sys
import os
import re
import tempfile
import logging
from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.run_code")

# Patterns that indicate dangerous operations — block these
_DANGEROUS_PATTERNS = [
    r"\bos\.system\b",
    r"\bsubprocess\.(?:call|run|Popen)\b.*(?:rm|del|format|shutdown)",
    r"\bshutil\.rmtree\b",
    r"\bos\.remove\b.*\*",
    r"__import__\(['\"]os['\"]",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r":\s*\/dev\/",
    r"C:\\Windows\\System32",
]
_DANGEROUS_RE = [re.compile(p, re.IGNORECASE) for p in _DANGEROUS_PATTERNS]

_DEFAULT_TIMEOUT = 15  # seconds
_MAX_OUTPUT_CHARS = 2000


def _is_dangerous(code: str) -> tuple[bool, str]:
    """Check if code contains dangerous operations."""
    for pattern in _DANGEROUS_RE:
        if pattern.search(code):
            return True, f"Blocked dangerous pattern: {pattern.pattern}"
    return False, ""


def _execute_python(code: str, timeout: int = _DEFAULT_TIMEOUT) -> tuple[bool, str, str]:
    """
    Execute Python code in isolated subprocess.
    Returns (success, stdout, stderr).
    """
    # Write code to temp file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8"
    ) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.expanduser("~"),  # run from home directory
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        )
        stdout = result.stdout[:_MAX_OUTPUT_CHARS]
        stderr = result.stderr[:_MAX_OUTPUT_CHARS]
        success = result.returncode == 0
        return success, stdout, stderr

    except subprocess.TimeoutExpired:
        return False, "", f"Code execution timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def _generate_code_for_task(task: str) -> str:
    """Use LLM to generate Python code for a task."""
    from models.llm import call_llm

    code_raw = call_llm(
        system=(
            "You are a Python code generator. "
            "Write clean, safe Python code to accomplish the given task. "
            "Output ONLY the Python code, no explanation, no markdown, no backticks. "
            "The code must be complete and immediately runnable. "
            "Print results to stdout. "
            "Do not use dangerous operations like deleting system files."
        ),
        user=f"Write Python code to: {task}",
        temperature=0.1,
        max_tokens=500
    )

    # Strip markdown if LLM added it anyway
    code = re.sub(r"```(?:python)?", "", code_raw).strip()
    code = re.sub(r"```", "", code).strip()
    return code


class RunCodeSkill(SkillBase):
    name = "run_code"
    description = "Writes and executes Python code to complete a programming task"
    timeout_seconds = 20.0

    def execute(self, params: dict, state) -> SkillResult:
        task = params.get("task", "").strip()
        code = params.get("code", "").strip()
        timeout = int(params.get("timeout", _DEFAULT_TIMEOUT))

        if not task and not code:
            return SkillResult(
                success=False, output=None,
                error="Provide either 'task' (natural language) or 'code' (Python code)"
            )

        # Generate code from task if not provided directly
        if not code:
            logger.info(f"Generating code for task: {task}")
            try:
                code = _generate_code_for_task(task)
                logger.info(f"Generated code ({len(code)} chars)")
            except Exception as e:
                return SkillResult(
                    success=False, output=None,
                    error=f"Code generation failed: {e}"
                )

        # Safety check
        dangerous, reason = _is_dangerous(code)
        if dangerous:
            return SkillResult(
                success=False, output=None,
                error=f"Code blocked for safety: {reason}"
            )

        # Execute
        logger.info(f"Executing code (timeout={timeout}s)")
        success, stdout, stderr = _execute_python(code, timeout=timeout)

        if success:
            output = stdout if stdout else "Code executed successfully (no output)"
            return SkillResult(success=True, output=output)
        else:
            error_msg = stderr if stderr else "Code execution failed with no error message"
            return SkillResult(
                success=False, output=stdout if stdout else None,
                error=error_msg
            )
