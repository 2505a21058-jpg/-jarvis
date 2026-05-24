"""
agent/executor.py

Execution layer for Jarvis.
All skill execution goes through this module.

Responsibilities:
- Execute skills by name with params
- Retry transient failures
- Enforce per-skill timeouts
- Return structured ExecutionResult
- Log every execution with timing
- Preserve plan execution and verification hooks used by agent/act.py
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from skills.base import SkillResult
from skills.registry import SkillRegistry

from permissions.policy import PolicyEngine, PolicyResult


logger = logging.getLogger("jarvis.executor")

_DEFAULT_TIMEOUT = float(os.getenv("JARVIS_EXECUTOR_TIMEOUT", "10"))
_DEFAULT_RETRIES = int(os.getenv("JARVIS_EXECUTOR_RETRIES", "2"))
_RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError, OSError)
_RETRYABLE_ERROR_TEXT = ("timeout", "connection", "not found", "unavailable", "temporarily", "busy")
_SKILL_TIMEOUT_OVERRIDES: dict[str, float] = {
    # Browser skills — match Playwright's timeout to avoid cascading
    "open_search_play":      60.0,
    "open_search_and_play":  60.0,
    "open_search":           45.0,
    "open_and_search":       45.0,
    "open_and_browse":       45.0,
    "open":                  45.0,
    "browse":                45.0,
    "web_summary":           50.0,
    "web_research":          60.0,
    "web_search":            45.0,
    "quick_search":          30.0,
    # PC skills
    "open_app":              30.0,
    "open_type":             25.0,
    "open_and_type":         25.0,
    "computer_control":  60.0,
    "codebase_explorer":     45.0,
    "deep_research":         120.0,
    "read_url":              40.0,
    # Fast skills
    "respond":               15.0,
    "system_monitor":         8.0,
    "reminder":               5.0,
    "list_skills":            3.0,
}

# Browser skills retry fewer times — each failure takes ~30s to timeout
_SKILL_RETRY_OVERRIDES: dict[str, int] = {
    "browse":                 1,
    "open":                   1,
    "open_search":            1,
    "open_and_search":        1,
    "open_and_browse":        1,
    "web_search":             1,
    "quick_search":           1,
    "open_search_play":       1,
    "open_search_and_play":   1,
}

STEP_SKILL_ALIASES = {
    "open": "open",
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
    "click_element": "gui_automate",
    "find_file": "system_search",
    "file_search": "system_search",
    "automate": "computer_control",
    "computer_control": "computer_control",
}


@dataclass
class ExecutionResult:
    success: bool
    output: Any = None
    error: str = ""
    elapsed_ms: float = 0.0
    skill_name: str = ""
    retries_used: int = 0
    metadata: dict = field(default_factory=dict)
    # Compatibility fields used by the existing planner/act pipeline.
    step_index: int = 0
    attempts: int = 1
    duration_ms: float = 0.0
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.duration_ms:
            self.duration_ms = self.elapsed_ms
        if not self.elapsed_ms:
            self.elapsed_ms = self.duration_ms
        if self.attempts < 1:
            self.attempts = self.retries_used + 1
        if not self.retries_used and self.attempts > 1:
            self.retries_used = self.attempts - 1
        self.error = str(self.error or "")

    def __str__(self) -> str:
        if self.success:
            return str(self.output) if self.output is not None else ""
        return f"Error: {self.error}"


@dataclass
class RetryPolicy:
    max_retries: int = _DEFAULT_RETRIES
    base_delay_ms: float = 200.0
    backoff_factor: float = 2.0
    retryable_errors: tuple[str, ...] = _RETRYABLE_ERROR_TEXT

    @property
    def max_attempts(self) -> int:
        return max(0, int(self.max_retries)) + 1

    def is_retryable(self, error: str) -> bool:
        if not error:
            return False
        error_lower = error.lower()
        return any(keyword in error_lower for keyword in self.retryable_errors)

    def delay_for_attempt(self, attempt: int) -> float:
        """Returns delay in seconds for a given retry attempt number (0-indexed)."""
        return (self.base_delay_ms * (self.backoff_factor ** attempt)) / 1000.0


# Skills that benefit from visual verification (opt-in via JARVIS_VISION_VERIFY=true)
_VISUALLY_VERIFIABLE = {
    "open_app": ("opened the application", "app window or application interface"),
    "browse": ("navigated to a URL", "web page content loaded in browser"),
    "open_and_type": ("opened app and typed text", "app with typed text visible"),
    "gui_automate": ("performed GUI action", "the action result on screen"),
    "computer_control": ("performed the desktop automation task", "the requested app or workflow result visible on screen"),
}

_VERIFIERS: dict[str, Callable] = {}
_PRE_HOOKS: list[Callable] = []
_POST_HOOKS: list[Callable] = []


class FailureCategory:
    TIMEOUT = "timeout"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    VERIFICATION = "verification"
    EXECUTION = "execution_error"
    VALIDATION = "validation_error"
    UNKNOWN = "unknown"

    _CATEGORY_PATTERNS = {
        TIMEOUT: ("timed out", "timeout", "deadline exceeded"),
        PERMISSION: ("permission denied", "not allowed", "denied", "unauthorized"),
        NOT_FOUND: ("not found", "no such", "unknown skill", "does not exist"),
        UNAVAILABLE: ("connection refused", "unavailable", "cannot connect", "service unavailable"),
        VERIFICATION: ("verification failed", "visual check failed", "unexpected screen state"),
        VALIDATION: ("missing required", "invalid param", "bad request", "required parameter"),
    }

    @classmethod
    def classify(cls, error_text: str) -> str:
        if not error_text:
            return cls.UNKNOWN
        lower = str(error_text).lower()
        for category, patterns in cls._CATEGORY_PATTERNS.items():
            if any(p in lower for p in patterns):
                return category
        return cls.EXECUTION


_POLICY_APPROVALS_KEY = "policy_approvals"


def _approval_context(state) -> dict | None:
    if state is None:
        return None
    if isinstance(state, dict):
        return state
    ui_context = getattr(state, "ui_context", None)
    if isinstance(ui_context, dict):
        return ui_context
    return None


def _state_user_input(state) -> str:
    if state is None:
        return ""
    if isinstance(state, dict):
        return str(state.get("user_input", ""))
    return str(getattr(state, "user_input", "") or "")


def approve_policy_action(state, skill_name: str) -> bool:
    """Register a one-use approval for a policy-confirmed skill."""
    context = _approval_context(state)
    if context is None:
        return False
    normalized = str(skill_name or "").strip().lower()
    approvals = context.setdefault(_POLICY_APPROVALS_KEY, [])
    if isinstance(approvals, list):
        approvals.append(normalized)
        return True
    if isinstance(approvals, set):
        approvals.add(normalized)
        return True
    if isinstance(approvals, dict):
        approvals[normalized] = True
        return True
    context[_POLICY_APPROVALS_KEY] = [normalized]
    return True


def _consume_policy_approval(state, skill_name: str) -> bool:
    context = _approval_context(state)
    if context is None:
        return False
    approvals = context.get(_POLICY_APPROVALS_KEY)
    normalized = str(skill_name or "").strip().lower()
    allowed = {normalized, "*"}

    if isinstance(approvals, list):
        for index, approval in enumerate(list(approvals)):
            if str(approval).strip().lower() in allowed:
                del approvals[index]
                return True
        return False

    if isinstance(approvals, set):
        for approval in list(approvals):
            if str(approval).strip().lower() in allowed:
                approvals.remove(approval)
                return True
        return False

    if isinstance(approvals, dict):
        for key in (normalized, "*"):
            if approvals.get(key):
                approvals.pop(key, None)
                return True
        return False

    return False


def register_pre_hook(fn: Callable) -> None:
    _PRE_HOOKS.append(fn)
    logger.debug("[EXECUTOR] pre_hook registered: %s", getattr(fn, "__name__", str(fn)))


def register_post_hook(fn: Callable) -> None:
    _POST_HOOKS.append(fn)
    logger.debug("[EXECUTOR] post_hook registered: %s", getattr(fn, "__name__", str(fn)))


def _resolve_skill_timeout(skill_name: str, skill, timeout: Optional[float]) -> float:
    if timeout is not None:
        return float(timeout)
    return float(
        _SKILL_TIMEOUT_OVERRIDES.get(
            skill_name,
            getattr(skill, "timeout_seconds", _DEFAULT_TIMEOUT),
        )
    )


def register_verifier(skill_name: str, fn: Callable) -> None:
    """Register a post-execution verifier for a skill."""
    _VERIFIERS[skill_name] = fn
    logger.debug("[EXECUTOR] verifier_registered skill=%s", skill_name)


def _verify(skill_name: str, result: SkillResult, params: dict, state) -> bool:
    """Run verifier if registered. Returns True if verified or no verifier exists."""
    verifier = _VERIFIERS.get(skill_name)
    if verifier is None:
        return True
    try:
        return bool(verifier(result, params, state))
    except Exception as exc:
        logger.warning("[EXECUTOR] verifier_failed skill=%s error=%s", skill_name, exc)
        return False


def _run_with_timeout(fn, kwargs: dict, timeout_s: float) -> Any:
    """
    Run fn(**kwargs) with a cross-platform timeout.
    Async results are awaited with asyncio.run() inside the worker thread.
    """
    result_box: list[Any] = [None]
    error_box: list[BaseException | None] = [None]
    done = threading.Event()
    cancel_event = threading.Event()
    call_kwargs = dict(kwargs or {})
    cancel_param = _cancel_event_parameter(fn)
    if cancel_param and cancel_param not in call_kwargs:
        call_kwargs[cancel_param] = cancel_event

    def target() -> None:
        try:
            result = fn(**call_kwargs)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            result_box[0] = result
        except BaseException as exc:
            error_box[0] = exc
        finally:
            done.set()

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    finished = done.wait(timeout=max(float(timeout_s or _DEFAULT_TIMEOUT), 0.1))

    if not finished:
        cancel_event.set()
        done.wait(timeout=min(max(float(timeout_s or _DEFAULT_TIMEOUT), 0.1), 1.0))
        raise TimeoutError(f"Skill timed out after {timeout_s}s")
    if error_box[0] is not None:
        raise error_box[0]
    return result_box[0]


def _cancel_event_parameter(fn: Callable) -> str | None:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return None

    for name in ("cancel_event", "cancellation_event", "timeout_event"):
        param = signature.parameters.get(name)
        if param and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
            return name

    if any(param.kind == param.VAR_KEYWORD for param in signature.parameters.values()):
        return "cancel_event"
    return None


class SkillExecutor:
    """
    Executes skills by name with retry, timeout, async-safe invocation, and verification.
    Singleton access is provided by get_executor().
    """

    def __init__(self, registry=None, retry_policy: RetryPolicy | None = None):
        self._registry = registry
        self._policy = retry_policy or RetryPolicy()
        self._stats: dict[str, dict[str, float | int]] = {}
        self._thread_pool = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="jarvis-skill",
        )

    def _get_registry(self):
        if self._registry is None:
            self._registry = SkillRegistry.instance()
        return self._registry

    def _policy_failure_result(
        self,
        skill_name: str,
        params: dict,
        step_index: int,
        reason: str,
        *,
        requires_confirmation: bool,
    ) -> ExecutionResult:
        metadata = {
            "params_keys": sorted(list((params or {}).keys())),
            "timeout_s": None,
            "retryable": False,
            "policy_result": reason,
            "requires_confirmation": requires_confirmation,
            "failure_category": FailureCategory.PERMISSION,
        }
        self._record_failure(skill_name)
        logger.warning("[EXECUTOR] skill=%s denied by policy: %s", skill_name, reason)
        return ExecutionResult(
            success=False,
            output=None,
            error=reason,
            elapsed_ms=0.0,
            duration_ms=0.0,
            skill_name=skill_name,
            step_index=step_index,
            verified=False,
            metadata=metadata,
        )

    def _check_policy_or_result(
        self,
        skill_name: str,
        params: dict,
        state,
        step_index: int,
    ) -> ExecutionResult | None:
        policy_check = PolicyEngine.instance().check(
            skill_name,
            params,
            user_input=_state_user_input(state),
        )
        if not policy_check.allowed:
            return self._policy_failure_result(
                skill_name,
                params,
                step_index,
                policy_check.reason or f"Skill '{skill_name}' denied by policy",
                requires_confirmation=False,
            )
        if policy_check.require_confirmation and not _consume_policy_approval(state, skill_name):
            reason = policy_check.reason or f"Skill '{skill_name}' requires confirmation"
            return self._policy_failure_result(
                skill_name,
                params,
                step_index,
                reason,
                requires_confirmation=True,
            )
        return None

    def execute(
        self,
        skill_name: str,
        params: dict,
        state=None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        step_index: int = 0,
        *,
        _policy_checked: bool = False,
    ) -> ExecutionResult:
        """
        Execute a skill by name. Always returns ExecutionResult and never raises.
        """
        normalized_name, normalized_params = self._normalize_step(skill_name, params or {})
        max_retries = int(self._policy.max_retries if retries is None else retries)
        max_retries = _SKILL_RETRY_OVERRIDES.get(normalized_name, max_retries)
        start = time.monotonic()
        last_error = ""
        retries_used = 0
        metadata = {
            "params_keys": sorted(list((normalized_params or {}).keys())),
            "timeout_s": None,
            "retryable": False,
        }
        if not _policy_checked:
            policy_failure = self._check_policy_or_result(normalized_name, normalized_params, state, step_index)
            if policy_failure is not None:
                return policy_failure

        for attempt in range(max_retries + 1):
            try:
                skill_result, effective_timeout = self._execute_once(
                    normalized_name,
                    normalized_params,
                    state,
                    timeout,
                )
                metadata["timeout_s"] = effective_timeout

                elapsed = (time.monotonic() - start) * 1000
                if skill_result.success:
                    verified = self._verify_success(normalized_name, skill_result, normalized_params, state)
                    if verified:
                        self._record_success(normalized_name, elapsed)
                        metadata["failure_category"] = None
                        for hook in _POST_HOOKS:
                            try:
                                hook(normalized_name, normalized_params, skill_result, None)
                            except Exception:
                                pass
                        logger.info(
                            "[EXECUTOR] skill=%s success=true elapsed_ms=%.2f attempts=%s verified=%s",
                            normalized_name,
                            elapsed,
                            attempt + 1,
                            verified,
                        )
                        return ExecutionResult(
                            success=True,
                            output=skill_result.output,
                            error="",
                            elapsed_ms=elapsed,
                            duration_ms=elapsed,
                            skill_name=normalized_name,
                            retries_used=retries_used,
                            attempts=attempt + 1,
                            step_index=step_index,
                            verified=True,
                            metadata=metadata,
                        )
                    last_error = "Verification failed"
                else:
                    last_error = str(skill_result.error or "Unknown error")

                metadata["retryable"] = self._policy.is_retryable(last_error)
                logger.warning(
                    "[EXECUTOR] skill=%s success=false attempt=%s/%s error=%s retryable=%s",
                    normalized_name,
                    attempt + 1,
                    max_retries + 1,
                    last_error,
                    metadata["retryable"],
                )
                if attempt < max_retries and metadata["retryable"]:
                    retries_used += 1
                    time.sleep(self._policy.delay_for_attempt(attempt))
                    continue
                break

            except _RETRYABLE_EXCEPTIONS as exc:
                last_error = str(exc)
                metadata["retryable"] = True
                logger.warning(
                    "[EXECUTOR] skill=%s transient_error attempt=%s/%s error=%s",
                    normalized_name,
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )
                if attempt < max_retries:
                    retries_used += 1
                    time.sleep(self._policy.delay_for_attempt(attempt))
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                logger.error(
                    "[EXECUTOR] skill=%s non_retryable_error=%s\n%s",
                    normalized_name,
                    exc,
                    traceback.format_exc(),
                )
                break

        elapsed = (time.monotonic() - start) * 1000
        self._record_failure(normalized_name)
        metadata["failure_category"] = FailureCategory.classify(last_error)

        for hook in _POST_HOOKS:
            try:
                hook(normalized_name, normalized_params, None, last_error)
            except Exception:
                pass

        logger.error(
            "[EXECUTOR] skill=%s success=false elapsed_ms=%.2f retries_used=%s error=%s category=%s",
            normalized_name,
            elapsed,
            retries_used,
            last_error,
            metadata["failure_category"],
        )
        return ExecutionResult(
            success=False,
            output=None,
            error=last_error,
            elapsed_ms=elapsed,
            duration_ms=elapsed,
            skill_name=normalized_name,
            retries_used=retries_used,
            attempts=retries_used + 1,
            step_index=step_index,
            verified=False,
            metadata=metadata,
        )

    async def execute_async(
        self,
        skill_name: str,
        params: dict,
        state=None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        step_index: int = 0,
    ) -> ExecutionResult:
        """
        Async-safe skill execution.
        Blocking skills run in a thread pool so they do not stall the event loop.
        Skills marked is_async=True are awaited directly; async_safe=True sync
        skills run inline because they have declared themselves non-blocking.
        """
        normalized_name, normalized_params = self._normalize_step(skill_name, params or {})
        registry = self._get_registry()
        skill = registry.get(normalized_name)

        policy_failure = self._check_policy_or_result(normalized_name, normalized_params, state, step_index)
        if policy_failure is not None:
            return policy_failure

        user_input = str(getattr(state, "user_input", "") if state else "")
        for hook in _PRE_HOOKS:
            try:
                hook(normalized_name, normalized_params, user_input)
            except Exception as exc:
                logger.debug("[EXECUTOR] pre_hook skipped: %s", exc)

        if skill and (getattr(skill, "is_async", False) or getattr(skill, "async_safe", False)):
            return await self._execute_direct_async_path(
                normalized_name,
                normalized_params,
                state,
                timeout,
                step_index,
                skill,
            )

        loop = asyncio.get_running_loop()
        effective_timeout = _resolve_skill_timeout(normalized_name, skill, timeout)
        start = time.monotonic()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    self._thread_pool,
                    lambda: self.execute(
                        normalized_name,
                        normalized_params,
                        state,
                        timeout=timeout,
                        retries=retries,
                        step_index=step_index,
                        _policy_checked=True,
                    ),
                ),
                timeout=effective_timeout + 2,
            )
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            self._record_failure(normalized_name)
            logger.error(
                "[EXECUTOR] skill=%s async_thread_pool_timeout elapsed_ms=%.2f timeout_s=%.2f",
                normalized_name,
                elapsed,
                effective_timeout,
            )
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Skill timed out in thread pool after {effective_timeout}s",
                elapsed_ms=elapsed,
                duration_ms=elapsed,
                skill_name=normalized_name,
                step_index=step_index,
                verified=False,
            )

    async def _execute_direct_async_path(
        self,
        skill_name: str,
        params: dict,
        state,
        timeout: Optional[float],
        step_index: int,
        skill,
    ) -> ExecutionResult:
        start = time.monotonic()
        effective_timeout = _resolve_skill_timeout(skill_name, skill, timeout)
        metadata = {
            "params_keys": sorted(list((params or {}).keys())),
            "timeout_s": effective_timeout,
            "retryable": False,
            "async_path": "native" if getattr(skill, "is_async", False) else "safe_inline",
        }

        registry = self._get_registry()
        entry = registry.get_entry(skill_name) if hasattr(registry, "get_entry") else None
        if entry is not None:
            entry.call_count += 1

        try:
            logger.info(
                "[EXECUTOR] async executing skill=%s params=%s timeout_s=%.2f path=%s",
                skill_name,
                sorted(list((params or {}).keys())),
                effective_timeout,
                metadata["async_path"],
            )
            if getattr(skill, "is_async", False):
                raw_result = await asyncio.wait_for(
                    self._invoke_async_skill(skill, params or {}, state),
                    timeout=effective_timeout,
                )
            else:
                raw_result = self._invoke_skill(skill, params or {}, state)
                if inspect.isawaitable(raw_result):
                    raw_result = await asyncio.wait_for(raw_result, timeout=effective_timeout)

            skill_result = self._normalize_skill_result(raw_result, skill_name)
            elapsed = (time.monotonic() - start) * 1000

            if skill_result.success:
                verified = self._verify_success(skill_name, skill_result, params, state)
                if verified:
                    self._record_success(skill_name, elapsed)
                    return ExecutionResult(
                        success=True,
                        output=skill_result.output,
                        error="",
                        elapsed_ms=elapsed,
                        duration_ms=elapsed,
                        skill_name=skill_name,
                        step_index=step_index,
                        attempts=1,
                        verified=True,
                        metadata=metadata,
                    )
                error = "Verification failed"
            else:
                error = str(skill_result.error or "Unknown error")

            if entry is not None:
                entry.error_count += 1
            self._record_failure(skill_name)
            return ExecutionResult(
                success=False,
                output=None,
                error=error,
                elapsed_ms=elapsed,
                duration_ms=elapsed,
                skill_name=skill_name,
                step_index=step_index,
                attempts=1,
                verified=False,
                metadata=metadata,
            )
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            if entry is not None:
                entry.error_count += 1
            self._record_failure(skill_name)
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Async skill timed out after {effective_timeout}s",
                elapsed_ms=elapsed,
                duration_ms=elapsed,
                skill_name=skill_name,
                step_index=step_index,
                attempts=1,
                verified=False,
                metadata=metadata,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            if entry is not None:
                entry.error_count += 1
            self._record_failure(skill_name)
            logger.error(
                "[EXECUTOR] skill=%s async_error=%s\n%s",
                skill_name,
                exc,
                traceback.format_exc(),
            )
            return ExecutionResult(
                success=False,
                output=None,
                error=str(exc),
                elapsed_ms=elapsed,
                duration_ms=elapsed,
                skill_name=skill_name,
                step_index=step_index,
                attempts=1,
                verified=False,
                metadata=metadata,
            )

    def _execute_once(self, skill_name: str, params: dict, state, timeout: Optional[float]) -> tuple[SkillResult, float]:
        registry = self._get_registry()
        skill = registry.get(skill_name)
        if skill is None:
            raise ValueError(f"Skill not found: {skill_name}")

        effective_timeout = _resolve_skill_timeout(skill_name, skill, timeout)
        logger.info("[EXECUTOR] executing skill=%s params=%s timeout_s=%.2f", skill_name, sorted(list((params or {}).keys())), effective_timeout)

        entry = registry.get_entry(skill_name) if hasattr(registry, "get_entry") else None
        if entry is not None:
            entry.call_count += 1

        try:
            raw_result = _run_with_timeout(
                self._invoke_skill,
                {"skill": skill, "params": params or {}, "state": state},
                effective_timeout,
            )
            result = self._normalize_skill_result(raw_result, skill_name)
            if entry is not None and not result.success:
                entry.error_count += 1
            return result, effective_timeout
        except Exception:
            if entry is not None:
                entry.error_count += 1
            raise

    @staticmethod
    def _invoke_skill(skill, params: dict, state, cancel_event: threading.Event | None = None) -> Any:
        execute = skill.execute
        signature = inspect.signature(execute)
        if cancel_event is not None:
            cancel_param = _cancel_event_parameter(execute)
            if cancel_param:
                return execute(params, state, **{cancel_param: cancel_event})
        if "state" in signature.parameters:
            return execute(params, state)
        if len(signature.parameters) >= 2:
            return execute(params, state)
        return execute(params)

    @staticmethod
    async def _invoke_async_skill(skill, params: dict, state) -> Any:
        raw_result = SkillExecutor._invoke_skill(skill, params, state)
        if inspect.isawaitable(raw_result):
            return await raw_result
        return raw_result

    @staticmethod
    def _normalize_skill_result(raw_result: Any, skill_name: str) -> SkillResult:
        if isinstance(raw_result, SkillResult):
            return raw_result
        if isinstance(raw_result, dict) and "success" in raw_result:
            return SkillResult(
                success=bool(raw_result.get("success")),
                output=raw_result.get("output"),
                error=raw_result.get("error"),
                skill_name=skill_name,
            )
        return SkillResult(success=True, output=raw_result, error=None, skill_name=skill_name)

    def _verify_success(self, skill_name: str, result: SkillResult, params: dict, state) -> bool:
        verified = _verify(skill_name, result, params, state)
        if not verified:
            return False

        if skill_name in _VISUALLY_VERIFIABLE and os.environ.get("JARVIS_VISION_VERIFY", "false").lower() == "true":
            try:
                from agent.screen_verify import verify_action_with_screenshot

                action_desc, expected = _VISUALLY_VERIFIABLE[skill_name]
                visual_ok, explanation = verify_action_with_screenshot(
                    action_description=action_desc,
                    expected_outcome=expected,
                    wait_seconds=1.5,
                )
                if not visual_ok:
                    logger.warning("[EXECUTOR] visual_verification_failed skill=%s explanation=%s", skill_name, explanation)
                    return False
            except Exception as exc:
                logger.debug("[EXECUTOR] visual_verification_skipped skill=%s error=%s", skill_name, exc)

        return True

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
                                success=False,
                                output=None,
                                error="Blocked by failed dependency",
                                step_index=step.index,
                                skill_name=step.skill_name,
                            )
                        )
                        remaining.remove(step)
                if not remaining:
                    break
                logger.error("[EXECUTOR] no_ready_steps remaining=%s", len(remaining))
                break

            if len(ready) == 1:
                step = ready[0]
                resolved_params = self._resolve_params(step.params, context)
                skill_name, normalized_params = self._normalize_step(step.skill_name, resolved_params)
                exec_result = self.execute(skill_name, normalized_params, state, step_index=step.index)
                results.append(exec_result)
                remaining.remove(step)
                if exec_result.success and step.output_key:
                    context[step.output_key] = exec_result.output
                    context[f"step_{step.index}_result"] = exec_result.output
            else:
                logger.debug("[EXECUTOR] running_parallel count=%s", len(ready))
                with ThreadPoolExecutor(max_workers=min(len(ready), 4)) as pool:
                    future_to_step = {
                        pool.submit(
                            self.execute,
                            *self._normalize_step(
                                step.skill_name,
                                self._resolve_params(step.params, context),
                            ),
                            state,
                            None,
                            None,
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
                                success=False,
                                output=None,
                                error=str(exc),
                                step_index=step.index,
                                skill_name=step.skill_name,
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
        raw_name = str(skill_name or "").strip().lower()
        normalized_name = STEP_SKILL_ALIASES.get(raw_name, raw_name)
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

        if normalized_name == "gui_automate":
            if raw_name == "click_element":
                payload.setdefault("action", "click")
            return normalized_name, payload

        return normalized_name, payload

    def _record_success(self, name: str, elapsed_ms: float) -> None:
        stats = self._stats.setdefault(name, {"calls": 0, "failures": 0, "total_ms": 0.0})
        stats["calls"] += 1
        stats["total_ms"] += elapsed_ms

    def _record_failure(self, name: str) -> None:
        stats = self._stats.setdefault(name, {"calls": 0, "failures": 0, "total_ms": 0.0})
        stats["calls"] += 1
        stats["failures"] += 1

    def get_stats(self) -> dict:
        return {name: dict(values) for name, values in self._stats.items()}

    def shutdown(self):
        """Cleanly shut down the async execution thread pool."""
        self._thread_pool.shutdown(wait=False)
        logger.info("[EXECUTOR] Thread pool shut down")


# Backward-compatible name used by agent/act.py.
Executor = SkillExecutor


def _verify_open_app(result: SkillResult, params: dict, state) -> bool:
    """Verify app was opened by checking if output mentions success."""
    return result.success and result.output is not None


def _verify_browse(result: SkillResult, params: dict, state) -> bool:
    """Verify browse succeeded by checking output is non-empty."""
    return result.success and bool(result.output)


register_verifier("open_app", _verify_open_app)
register_verifier("browse", _verify_browse)


_executor: Optional[SkillExecutor] = None


def get_executor() -> SkillExecutor:
    global _executor
    if _executor is None:
        _executor = SkillExecutor()
    return _executor
