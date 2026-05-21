from __future__ import annotations

import asyncio
import inspect
import threading
import time

from agent.executor import RetryPolicy, SkillExecutor
from skills.base import SkillResult


class FakeEntry:
    def __init__(self, skill):
        self.skill = skill
        self.call_count = 0
        self.error_count = 0


class FakeRegistry:
    def __init__(self, skills):
        self.entries = {name: FakeEntry(skill) for name, skill in skills.items()}

    def get(self, name):
        entry = self.entries.get(name)
        return entry.skill if entry else None

    def get_entry(self, name):
        return self.entries.get(name)


class SyncSkill:
    timeout_seconds = 1.0

    def execute(self, params, state):
        return SkillResult(success=True, output=f"hello {params['name']}:{state['mode']}")


class RetrySkill:
    timeout_seconds = 1.0

    def __init__(self):
        self.calls = 0

    def execute(self, params, state):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("temporary timeout")
        return SkillResult(success=True, output="recovered")


class TimeoutSkill:
    timeout_seconds = 1.0

    def execute(self, params, state):
        time.sleep(0.2)
        return SkillResult(success=True, output="too late")


class AsyncSkill:
    timeout_seconds = 1.0

    async def execute(self, params, state):
        return SkillResult(success=True, output="async ok")


class AsyncNativeSkill:
    is_async = True
    timeout_seconds = 1.0

    async def execute(self, params, state):
        await asyncio.sleep(0)
        return SkillResult(success=True, output=threading.current_thread().name)


class SlowBlockingSkill:
    timeout_seconds = 1.0

    def execute(self, params, state):
        time.sleep(0.15)
        return SkillResult(success=True, output="done")


class AsyncSafeSkill:
    async_safe = True
    timeout_seconds = 1.0

    def execute(self, params, state):
        return SkillResult(success=True, output=threading.current_thread().name)


class FailedSkill:
    timeout_seconds = 1.0

    def execute(self, params, state):
        return SkillResult(success=False, output=None, error="validation failed")


class EchoSkill:
    timeout_seconds = 1.0

    def execute(self, params, state):
        return SkillResult(success=True, output=params)


def test_executor_success_result_shape():
    executor = SkillExecutor(registry=FakeRegistry({"sync": SyncSkill()}))

    result = executor.execute("sync", {"name": "jarvis"}, {"mode": "fast"})

    assert result.success is True
    assert result.output == "hello jarvis:fast"
    assert result.elapsed_ms >= 0
    assert result.duration_ms == result.elapsed_ms
    assert result.retries_used == 0
    assert result.metadata["params_keys"] == ["name"]
    assert str(result) == "hello jarvis:fast"


def test_executor_retries_retryable_exception(monkeypatch):
    skill = RetrySkill()
    executor = SkillExecutor(
        registry=FakeRegistry({"retry": skill}),
        retry_policy=RetryPolicy(max_retries=1, base_delay_ms=1),
    )
    monkeypatch.setattr("agent.executor.time.sleep", lambda seconds: None)

    result = executor.execute("retry", {}, {})

    assert result.success is True
    assert result.output == "recovered"
    assert result.retries_used == 1
    assert skill.calls == 2


def test_executor_timeout_returns_failure():
    executor = SkillExecutor(registry=FakeRegistry({"slow": TimeoutSkill()}), retry_policy=RetryPolicy(max_retries=0))

    result = executor.execute("slow", {}, {}, timeout=0.01)

    assert result.success is False
    assert "timed out" in result.error.lower()
    assert str(result).startswith("Error:")


def test_executor_uses_browser_skill_timeout_override(monkeypatch):
    captured = {}

    def fake_run_with_timeout(fn, kwargs, timeout_s):
        captured["timeout_s"] = timeout_s
        return fn(**kwargs)

    monkeypatch.setattr("agent.executor._run_with_timeout", fake_run_with_timeout)
    executor = SkillExecutor(registry=FakeRegistry({"open_and_search": EchoSkill()}))

    result = executor.execute("open_and_search", {"query": "python"}, {})

    assert result.success is True
    assert captured["timeout_s"] == 45.0


def test_executor_runs_async_skill():
    executor = SkillExecutor(registry=FakeRegistry({"async": AsyncSkill()}))

    result = executor.execute("async", {}, {})

    assert result.success is True
    assert result.output == "async ok"


def test_execute_async_is_coroutine_function():
    assert inspect.iscoroutinefunction(SkillExecutor.execute_async)


def test_execute_async_runs_blocking_skill_without_stalling_event_loop():
    executor = SkillExecutor(registry=FakeRegistry({"slow": SlowBlockingSkill()}))

    try:
        async def run():
            skill_task = asyncio.create_task(executor.execute_async("slow", {}, {}))
            start = time.monotonic()
            await asyncio.sleep(0.01)
            marker_elapsed = time.monotonic() - start
            result = await skill_task
            return marker_elapsed, result

        marker_elapsed, result = asyncio.run(run())
    finally:
        shutdown = getattr(executor, "shutdown", None)
        if callable(shutdown):
            shutdown()

    assert marker_elapsed < 0.1
    assert result.success is True
    assert result.output == "done"


def test_execute_async_awaits_async_native_skill_directly():
    executor = SkillExecutor(registry=FakeRegistry({"native": AsyncNativeSkill()}))

    try:
        result = asyncio.run(executor.execute_async("native", {}, {}))
    finally:
        shutdown = getattr(executor, "shutdown", None)
        if callable(shutdown):
            shutdown()

    assert result.success is True
    assert result.output == threading.current_thread().name


def test_execute_async_runs_async_safe_sync_skill_directly():
    executor = SkillExecutor(registry=FakeRegistry({"safe": AsyncSafeSkill()}))

    try:
        result = asyncio.run(executor.execute_async("safe", {}, {}))
    finally:
        shutdown = getattr(executor, "shutdown", None)
        if callable(shutdown):
            shutdown()

    assert result.success is True
    assert result.output == threading.current_thread().name


def test_executor_failed_skill_result_is_not_retried_by_default():
    executor = SkillExecutor(registry=FakeRegistry({"failed": FailedSkill()}), retry_policy=RetryPolicy(max_retries=2))

    result = executor.execute("failed", {}, {})

    assert result.success is False
    assert result.error == "validation failed"
    assert result.retries_used == 0


def test_executor_normalizes_gemma_action_aliases():
    executor = SkillExecutor(
        registry=FakeRegistry(
            {
                "gui_automate": EchoSkill(),
                "system_search": EchoSkill(),
            }
        )
    )

    click_result = executor.execute("click_element", {"element": "Search"}, {})
    file_result = executor.execute("find_file", {"query": "notes.txt"}, {})

    assert click_result.success is True
    assert click_result.output == {"element": "Search", "action": "click"}
    assert file_result.success is True
    assert file_result.output == {"query": "notes.txt"}
