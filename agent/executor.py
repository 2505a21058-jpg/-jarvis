"""
agent/executor.py

Reliable skill execution layer for Jarvis.
Wraps SkillRegistry with:
  - Configurable retry with backoff
  - Post-execution verification hooks
  - Parallel execution for independent plan steps
  - Failure classification (transient vs permanent)
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

from skills.base import SkillResult
from skills.registry import SkillRegistry


logger = logging.getLogger("jarvis.executor")

STEP_SKILL_ALIASES = {
    "open": "open_app",
    "open_app": "open_app",
    "search": "browse",
    "search_web": "browse",
    "browse": "browse",
    "find": "browse",
    "watch": "browse",
    "play": "browse",
    "play_music": "browse",
    "type": "type_text",
    "type_text": "type_text",
}


@dataclass
class ExecutionResult:
    step_index: int
    skill_name: str
    success: bool
    output: object
    error: Optional[str] = None
    attempts: int = 1
    duration_ms: float = 0.0
    verified: bool = False


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_ms: float = 200.0
    backoff_factor: float = 2.0
    retryable_errors: tuple = ("timeout", "connection", "not found", "unavailable")

    def is_retryable(self, error: str) -> bool:
        if not error:
            return False
        error_lower = error.lower()
        return any(keyword in error_lower for keyword in self.retryable_errors)

    def delay_for_attempt(self, attempt: int) -> float:
        """Returns delay in seconds for a given attempt number (0-indexed)."""
        return (self.base_delay_ms * (self.backoff_factor ** attempt)) / 1000.0


# Skills that benefit from visual verification (opt-in via JARVIS_VISION_VERIFY=true)
_VISUALLY_VERIFIABLE = {
    "open_app": ("opened the application", "app window or application interface"),
    "browse": ("navigated to a URL", "web page content loaded in browser"),
    "open_and_type": ("opened app and typed text", "app with typed text visible"),
    "gui_automate": ("performed GUI action", "the action result on screen"),
}

_VERIFIERS: dict[str, Callable] = {}


def register_verifier(skill_name: str, fn: Callable) -> None:
    """Register a post-execution verifier for a skill."""
    _VERIFIERS[skill_name] = fn
    logger.debug("Verifier registered for skill: %s", skill_name)


def _verify(skill_name: str, result: SkillResult, params: dict, state) -> bool:
    """Run verifier if registered. Returns True if verified or no verifier exists."""
    verifier = _VERIFIERS.get(skill_name)
    if verifier is None:
        return True
    try:
        return bool(verifier(result, params, state))
    except Exception as exc:
        logger.warning("Verifier for '%s' raised: %s", skill_name, exc)
        return False


class Executor:
    """
    Executes individual skills with retry and verification.
    Used by plan execution and direct skill calls.
    """

    def __init__(self, retry_policy: RetryPolicy = None):
        self._policy = retry_policy or RetryPolicy()
        self._registry = SkillRegistry.instance()

    def execute(self, skill_name: str, params: dict, state, step_index: int = 0) -> ExecutionResult:
        """Execute a skill with retry and verification."""
        start = time.monotonic()
        last_error = None

        for attempt in range(self._policy.max_attempts):
            if attempt > 0:
                delay = self._policy.delay_for_attempt(attempt - 1)
                logger.debug(
                    "Retry %s/%s for '%s' in %.2fs",
                    attempt,
                    self._policy.max_attempts,
                    skill_name,
                    delay,
                )
                time.sleep(delay)

            result = self._registry.execute(skill_name, params, state)

            if result.success:
                verified = _verify(skill_name, result, params, state)
                duration = (time.monotonic() - start) * 1000
                if not verified:
                    logger.warning(
                        "Skill '%s' succeeded but failed verification (attempt %s)",
                        skill_name,
                        attempt + 1,
                    )
                    last_error = "Verification failed"
                    if not self._policy.is_retryable(last_error):
                        break
                    continue

                # Optional screenshot-based visual verification
                if skill_name in _VISUALLY_VERIFIABLE:
                    vision_enabled = os.environ.get("JARVIS_VISION_VERIFY", "false").lower() == "true"
                    if vision_enabled:
                        try:
                            from agent.screen_verify import verify_action_with_screenshot
                            action_desc, expected = _VISUALLY_VERIFIABLE[skill_name]
                            visual_ok, explanation = verify_action_with_screenshot(
                                action_description=action_desc,
                                expected_outcome=expected,
                                wait_seconds=1.5
                            )
                            if not visual_ok:
                                logger.warning(
                                    "Visual verification failed for '%s': %s",
                                    skill_name,
                                    explanation,
                                )
                                result.success = False
                                result.error = f"Action may not have completed: {explanation}"
                                last_error = result.error
                                if not self._policy.is_retryable(last_error):
                                    break
                                continue
                        except Exception as e:
                            logger.debug("Visual verification skipped: %s", e)

                return ExecutionResult(
                    step_index=step_index,
                    skill_name=skill_name,
                    success=True,
                    output=result.output,
                    attempts=attempt + 1,
                    duration_ms=duration,
                    verified=True,
                )

            last_error = result.error or "Unknown error"
            logger.warning("Skill '%s' failed (attempt %s): %s", skill_name, attempt + 1, last_error)
            if not self._policy.is_retryable(last_error):
                logger.debug("Error not retryable, stopping: %s", last_error)
                break

        duration = (time.monotonic() - start) * 1000
        return ExecutionResult(
            step_index=step_index,
            skill_name=skill_name,
            success=False,
            output=None,
            error=last_error,
            attempts=min(self._policy.max_attempts, 3),
            duration_ms=duration,
            verified=False,
        )

    def execute_plan(self, steps: list, state) -> tuple[list[ExecutionResult], dict]:
        """
        Execute a list of Plan Steps.
        Steps with no depends_on and different output_keys are run in parallel.
        Returns (results_list, execution_context).
        """
        context: dict = {}
        results: list[ExecutionResult] = []
        remaining = list(steps)

        while remaining:
            successful_indices = {result.step_index for result in results if result.success}
            ready = [
                step
                for step in remaining
                if all(dependency in successful_indices for dependency in list(step.depends_on or []))
            ]

            if not ready:
                failed_indices = {result.step_index for result in results if not result.success}
                blocked = [
                    step
                    for step in remaining
                    if any(dependency in failed_indices for dependency in list(step.depends_on or []))
                ]
                if blocked:
                    for step in blocked:
                        results.append(
                            ExecutionResult(
                                step_index=step.index,
                                skill_name=step.skill_name,
                                success=False,
                                output=None,
                                error="Blocked by failed dependency",
                            )
                        )
                        remaining.remove(step)
                if not remaining:
                    break
                logger.error("Executor: no steps ready and no blocked steps - breaking")
                break

            if len(ready) == 1:
                step = ready[0]
                resolved_params = self._resolve_params(step.params, context)
                skill_name, normalized_params = self._normalize_step(step.skill_name, resolved_params)
                exec_result = self.execute(skill_name, normalized_params, state, step.index)
                results.append(exec_result)
                remaining.remove(step)
                if exec_result.success and step.output_key:
                    context[step.output_key] = exec_result.output
                    context[f"step_{step.index}_result"] = exec_result.output
            else:
                logger.debug("Running %s steps in parallel", len(ready))
                with ThreadPoolExecutor(max_workers=min(len(ready), 4)) as pool:
                    future_to_step = {
                        pool.submit(
                            self.execute,
                            *self._normalize_step(
                                step.skill_name,
                                self._resolve_params(step.params, context),
                            ),
                            state,
                            step.index,
                        ): step
                        for step in ready
                    }
                    for future in as_completed(future_to_step):
                        step = future_to_step[future]
                        try:
                            exec_result = future.result()
                        except Exception as exc:
                            exec_result = ExecutionResult(
                                step_index=step.index,
                                skill_name=step.skill_name,
                                success=False,
                                output=None,
                                error=str(exc),
                            )
                        results.append(exec_result)
                        remaining.remove(step)
                        if exec_result.success and step.output_key:
                            context[step.output_key] = exec_result.output
                            context[f"step_{step.index}_result"] = exec_result.output

        return results, context

    @staticmethod
    def _resolve_params(params: dict, context: dict) -> dict:
        resolved = {}
        for key, value in (params or {}).items():
            if isinstance(value, str):
                try:
                    resolved[key] = value.format(**context)
                except KeyError:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _normalize_step(skill_name: str, params: dict) -> tuple[str, dict]:
        normalized_name = STEP_SKILL_ALIASES.get(str(skill_name or "").strip().lower(), str(skill_name or "").strip().lower())
        payload = dict(params or {})

        if normalized_name == "open_app":
            app = str(payload.get("app") or payload.get("target") or payload.get("app_name") or "").strip()
            normalized = {"app": app}
            if payload.get("url"):
                normalized["url"] = str(payload.get("url")).strip()
            return normalized_name, normalized

        if normalized_name == "browse":
            url = str(payload.get("url") or "").strip()
            query = str(payload.get("query") or payload.get("target") or payload.get("text") or "").strip()
            return normalized_name, {"url": url} if url else {"query": query}

        if normalized_name == "type_text":
            text = str(payload.get("text") or payload.get("target") or "").strip()
            return normalized_name, {"text": text}

        return normalized_name, payload


def _verify_open_app(result: SkillResult, params: dict, state) -> bool:
    """Verify app was opened by checking if output mentions success."""
    return result.success and result.output is not None


def _verify_browse(result: SkillResult, params: dict, state) -> bool:
    """Verify browse succeeded by checking output is non-empty."""
    return result.success and bool(result.output)


register_verifier("open_app", _verify_open_app)
register_verifier("browse", _verify_browse)


_executor: Optional[Executor] = None


def get_executor() -> Executor:
    global _executor
    if _executor is None:
        _executor = Executor()
    return _executor
