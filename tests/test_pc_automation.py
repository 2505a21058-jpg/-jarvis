from __future__ import annotations


def test_pc_import_chain_and_aliases():
    from skills.automation.pc.app_launcher import is_browser_app, resolve_app
    from skills.automation.pc.controller import get_pc

    assert get_pc() is get_pc()
    assert resolve_app("notepad") == "notepad"
    assert resolve_app("vs code") == "code"
    assert is_browser_app("youtube") is True


def test_window_fragments_cover_vscode_aliases():
    from skills.automation.pc.app_launcher import _window_fragments

    fragments = _window_fragments("vs code")
    assert "vs code" in fragments
    assert "visual studio code" in fragments
    assert "code" in fragments


def test_pc_controller_open_and_type_uses_window_wait_instead_of_sleep(monkeypatch):
    from skills.automation.pc.controller import PCController

    calls = []
    monkeypatch.setattr(PCController, "open_app", lambda self, app: calls.append(("open", app)) or f"Opened {app}")
    monkeypatch.setattr("skills.automation.pc.app_launcher.wait_for_window", lambda app, timeout=10: calls.append(("wait", app, timeout)) or True)
    monkeypatch.setattr("skills.automation.pc.app_launcher.bring_to_front", lambda app: calls.append(("front", app)) or True)
    monkeypatch.setattr(PCController, "type_text", lambda self, text: calls.append(("type", text)) or f"Typed: {text}")

    result = PCController().open_and_type("notepad", "hello", wait_s=2.0)

    assert result == "Opened notepad. Typed: hello"
    assert calls == [
        ("open", "notepad"),
        ("wait", "notepad", 2),
        ("front", "notepad"),
        ("type", "hello"),
    ]


def test_open_app_routes_web_apps_to_browser_actions(monkeypatch):
    from skills.open_app import OpenAppSkill

    opened = []
    monkeypatch.setattr(
        "skills.automation.browser.actions.navigate_sync",
        lambda url: opened.append(url) or f"Opened {url}",
    )

    state = {}
    result = OpenAppSkill().run({"app": "gmail"}, state)

    assert result.success is True
    assert opened == ["https://mail.google.com"]
    assert state["active_app"] == "browser"
    assert state["browser_url"] == "https://mail.google.com"


def test_open_app_uses_pc_controller_for_native_app(monkeypatch):
    from skills.open_app import OpenAppSkill

    class FakePC:
        def open_app(self, app_name: str) -> str:
            return f"Opened {app_name} via pc"

    monkeypatch.setattr("skills.automation.pc.controller.get_pc", lambda: FakePC())

    state = {}
    result = OpenAppSkill().run({"app": "notepad"}, state)

    assert result.success is True
    assert result.output == "Opened notepad via pc"
    assert state["active_app"] == "notepad"
