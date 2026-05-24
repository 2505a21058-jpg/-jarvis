from __future__ import annotations

from types import SimpleNamespace


def test_app_helpers_native_launch_does_not_use_shell(monkeypatch):
    from skills import app_helpers

    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(app_helpers.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(app_helpers.time, "sleep", lambda _: None)

    assert app_helpers.launch_and_prep("notepad") is True

    assert calls == [(["notepad"], {"shell": False})]


def test_app_helpers_url_fallback_uses_webbrowser_not_shell(monkeypatch):
    from skills import app_helpers

    opened = []
    monkeypatch.setattr(app_helpers, "_get_page", lambda context: (_ for _ in ()).throw(RuntimeError("no browser")))
    monkeypatch.setattr(
        app_helpers,
        "webbrowser",
        SimpleNamespace(open=lambda url: opened.append(url) or True),
        raising=False,
    )
    monkeypatch.setattr(
        app_helpers.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("URL fallback should not use shell")),
    )
    monkeypatch.setattr(app_helpers.time, "sleep", lambda _: None)

    assert app_helpers.launch_and_prep("youtube", context=object()) is True

    assert opened == ["https://youtube.com"]


def test_app_helpers_direct_url_open_uses_webbrowser_fallback(monkeypatch):
    from skills import app_helpers

    opened = []
    monkeypatch.setattr(app_helpers, "_get_page", lambda context: (_ for _ in ()).throw(RuntimeError("no browser")))
    monkeypatch.setattr(
        app_helpers,
        "webbrowser",
        SimpleNamespace(open=lambda url: opened.append(url) or True),
        raising=False,
    )
    monkeypatch.setattr(
        app_helpers.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("URL fallback should not use shell")),
    )
    monkeypatch.setattr(app_helpers.time, "sleep", lambda _: None)

    assert app_helpers.launch_and_prep("example.com", context=object()) is True

    assert opened == ["https://example.com"]


def test_pc_launcher_subprocess_does_not_use_shell(monkeypatch):
    from skills.automation.pc import app_launcher

    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(app_launcher.subprocess, "Popen", fake_popen)

    assert app_launcher._launch_subprocess("notepad") is True

    assert calls == [
        (
            ["notepad"],
            {
                "shell": False,
                "stdout": app_launcher.subprocess.DEVNULL,
                "stderr": app_launcher.subprocess.DEVNULL,
            },
        )
    ]


def test_pc_launcher_start_fallback_avoids_os_system(monkeypatch):
    from skills.automation.pc import app_launcher

    opened = []
    monkeypatch.setattr(app_launcher.os, "startfile", lambda target: opened.append(target), raising=False)
    monkeypatch.setattr(
        app_launcher.os,
        "system",
        lambda command: (_ for _ in ()).throw(AssertionError("os.system should not be used for app launch")),
    )

    assert app_launcher._launch_start("notepad") is True

    assert opened == ["notepad"]
