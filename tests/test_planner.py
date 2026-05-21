from __future__ import annotations

from agent.executor import ExecutionResult
from agent.planner import _build_planner_system, _validate_plan


def test_planner_allows_open_search_and_play():
    plan_data = {
        "goal": "open youtube, search telugu songs and play the first song",
        "steps": [
            {
                "index": 0,
                "skill_name": "open_search_and_play",
                "description": "Search YouTube and open the first result",
                "params": {"app": "youtube", "query": "telugu songs"},
                "depends_on": [],
                "output_key": "youtube_result",
            }
        ],
    }

    valid, reason = _validate_plan(plan_data)
    assert valid is True
    assert reason == ""


def test_planner_prompt_mentions_youtube_guardrails():
    prompt = _build_planner_system()
    assert "open_search_and_play" in prompt
    assert 'NEVER open "notepad"' in prompt
    assert "open_search_and_play with app=" in prompt


def test_planner_allows_computer_control():
    plan_data = {
        "goal": "open chrome search for trains to hyderabad and book one",
        "steps": [
            {
                "index": 0,
                "skill_name": "computer_control",
                "description": "Use general computer control for the full workflow",
                "params": {"task": "open chrome search for trains to hyderabad and book one"},
                "depends_on": [],
                "output_key": "automation_result",
            }
        ],
    }

    valid, reason = _validate_plan(plan_data)
    assert valid is True
    assert reason == ""


def test_planner_prompt_mentions_general_ui_workflows():
    prompt = _build_planner_system()
    assert "computer_control" in prompt
    assert "drawing" in prompt
    assert "bookings" in prompt


def test_plan_graph_topological_order_respects_dependencies():
    from agent.planner import PlanGraph, PlanStep

    graph = PlanGraph()
    graph.add(PlanStep("search", "open_and_search", {"app": "youtube", "query": "lofi"}))
    graph.add(PlanStep("play", "open_search_and_play", {"app": "youtube", "query": "lofi"}, depends_on=["search"]))

    assert graph.topological_order() == ["search", "play"]


def test_build_plan_from_steps_supports_existing_llm_step_shape():
    from agent.planner import build_plan_from_steps

    graph = build_plan_from_steps([
        {
            "index": 0,
            "skill_name": "open_app",
            "params": {"app": "chrome"},
            "depends_on": [],
            "description": "Open Chrome",
        },
        {
            "index": 1,
            "skill_name": "type_text",
            "params": {"text": "hello"},
            "depends_on": [0],
            "description": "Type hello",
        },
    ])

    assert graph.topological_order() == ["step_0", "step_1"]
    assert graph.steps["step_1"].depends_on == ["step_0"]


def test_execute_plan_passes_retry_and_timeout_to_executor(monkeypatch):
    import agent.planner as planner
    from agent.planner import PlanGraph, PlanStep, execute_plan

    calls = []

    class FakeExecutor:
        def execute(self, skill_name, params, state=None, timeout=None, retries=None):
            calls.append((skill_name, params, timeout, retries))
            return ExecutionResult(success=True, output=f"ran {skill_name}", skill_name=skill_name)

    monkeypatch.setattr(planner, "get_executor", lambda: FakeExecutor())
    graph = PlanGraph()
    graph.add(PlanStep("s1", "respond", {"message": "hello"}, retries=3, timeout=7))

    results = execute_plan(graph, state=None)

    assert results["s1"].success is True
    assert calls == [("respond", {"message": "hello"}, 7, 3)]
    assert graph.steps["s1"].status == "done"


def test_execute_plan_skips_steps_when_dependency_failed(monkeypatch):
    import agent.planner as planner
    from agent.planner import PlanGraph, PlanStep, execute_plan

    class FakeExecutor:
        def execute(self, skill_name, params, state=None, timeout=None, retries=None):
            return ExecutionResult(success=False, error="boom", skill_name=skill_name)

    monkeypatch.setattr(planner, "get_executor", lambda: FakeExecutor())
    graph = PlanGraph()
    graph.add(PlanStep("s1", "open_app"))
    graph.add(PlanStep("s2", "type_text", depends_on=["s1"]))

    results = execute_plan(graph, state=None)

    assert results["s1"].success is False
    assert graph.steps["s2"].status == "skipped"


def test_execute_plan_replan_hook_runs_replacement_step(monkeypatch):
    import agent.planner as planner
    from agent.planner import PlanGraph, PlanStep, execute_plan

    class FakeExecutor:
        def execute(self, skill_name, params, state=None, timeout=None, retries=None):
            if skill_name == "open_app":
                return ExecutionResult(success=False, error="not found", skill_name=skill_name)
            return ExecutionResult(success=True, output="fallback worked", skill_name=skill_name)

    monkeypatch.setattr(planner, "get_executor", lambda: FakeExecutor())
    graph = PlanGraph()
    graph.add(PlanStep("s1", "open_app", {"app": "missing"}))

    def replan_hook(step, result):
        return PlanStep("s1_recovery", "browse", {"url": "https://example.com"})

    results = execute_plan(graph, state=None, replan_hook=replan_hook)

    assert results["s1"].success is False
    assert results["s1_recovery"].success is True
    assert graph.steps["s1_recovery"].status == "done"
