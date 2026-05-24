from __future__ import annotations


def test_bootstrap_registers_router_and_legacy_skill_targets():
    import skills
    from skills.registry import SkillRegistry

    skills._BOOTSTRAPPED = False
    SkillRegistry._instance = None

    registry = skills.get_registry()
    expected = {
        "browse",
        "computer_control",
        "gui_automate",
        "open",
        "open_and_browse",
        "open_and_search",
        "open_and_type",
        "open_search",
        "open_search_and_play",
        "open_search_play",
        "open_type",
        "select",
        "type",
    }

    missing = sorted(name for name in expected if registry.get(name) is None)
    assert missing == []


def test_legacy_skill_modules_export_named_classes():
    from skills.browser import BrowseSkill
    from skills.computer_control import ComputerControlSkill
    from skills.gui_automate import GUIAutomateSkill
    from skills.open_and_search import OpenAndBrowseSkill, OpenAndSearchSkill
    from skills.open_and_type import OpenAndTypeSkill
    from skills.open_search_and_play import OpenSearchAndPlaySkill

    assert BrowseSkill.name == "browse"
    assert ComputerControlSkill.name == "computer_control"
    assert GUIAutomateSkill.name == "gui_automate"
    assert OpenAndBrowseSkill.name == "open_and_browse"
    assert OpenAndSearchSkill.name == "open_and_search"
    assert OpenAndTypeSkill.name == "open_and_type"
    assert OpenSearchAndPlaySkill.name == "open_search_and_play"


def test_web_browse_route_passes_url_to_open_template():
    from agent.intent.classifier import classify
    from agent.intent.router import route

    intent = classify("go to example.com")
    skill_name, params = route(intent)

    assert skill_name == "open"
    assert params["url"] == "https://example.com"
    assert params["app"] == "https://example.com"


def test_gui_click_route_passes_target_to_select_template():
    from agent.intent.classifier import classify
    from agent.intent.router import route

    intent = classify("click the search button")
    skill_name, params = route(intent)

    assert skill_name == "select"
    assert params["element"] == "search"
    assert params["target"] == "search"


def test_computer_use_route_preserves_policy_goal_and_runtime_task():
    from agent.intent.classifier import classify
    from agent.intent.router import route

    intent = classify("open vscode and create a new file")
    skill_name, params = route(intent)

    assert skill_name == "computer_control"
    assert params["goal"] == "open vscode and create a new file"
    assert params["task"] == "open vscode and create a new file"
