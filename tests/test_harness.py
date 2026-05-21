from __future__ import annotations


def test_launcher_uses_fixed_jarvis_profile_and_user_data_dir(monkeypatch):
    from agent.harness import launcher

    popen_calls = []

    class FakeProcess:
        pass

    def fake_popen(args, **kwargs):
        popen_calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(launcher, "_CHROME_EXE", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    monkeypatch.setattr(
        launcher,
        "_CHROME_USER_DATA",
        r"C:\Users\shiva\AppData\Local\Google\Chrome\User Data",
    )
    monkeypatch.setattr(launcher, "_CHROME_PROFILE", "Profile 3")
    monkeypatch.setattr(launcher.os.path, "exists", lambda path: True)
    monkeypatch.setattr(launcher, "is_chrome_debug_available", lambda port: True)
    monkeypatch.setattr(launcher.subprocess, "CREATE_NO_WINDOW", 134217728, raising=False)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    assert launcher._launch_chrome(9222) is True

    args, kwargs = popen_calls[0]
    assert args == [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        r"--user-data-dir=C:\Users\shiva\AppData\Local\Google\Chrome\User Data",
        "--profile-directory=Profile 3",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-extensions-except=",
        "--disable-default-apps",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    assert kwargs["creationflags"] == 134217728
    assert kwargs["stdout"] is launcher.subprocess.DEVNULL
    assert kwargs["stderr"] is launcher.subprocess.DEVNULL


def test_launcher_default_timeout_allows_slow_chrome_startup():
    from agent.harness import launcher

    assert launcher._LAUNCH_TIMEOUT == 35.0


def test_launcher_falls_back_to_isolated_user_data_when_primary_profile_is_locked(monkeypatch, tmp_path):
    from agent.harness import launcher

    popen_calls = []

    class FakeProcess:
        pass

    def fake_popen(args, **kwargs):
        popen_calls.append(args)
        return FakeProcess()

    monkeypatch.setattr(launcher, "_CHROME_EXE", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    monkeypatch.setattr(launcher, "_CHROME_USER_DATA", r"C:\Users\shiva\AppData\Local\Google\Chrome\User Data")
    monkeypatch.setattr(launcher, "_CHROME_FALLBACK_USER_DATA", str(tmp_path / "ChromeDebugUserData"))
    monkeypatch.setattr(launcher, "_CHROME_PROFILE", "Profile 3")
    monkeypatch.setattr(launcher, "_LAUNCH_TIMEOUT", 0.01)
    monkeypatch.setattr(launcher.os.path, "exists", lambda path: True)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(launcher, "is_chrome_debug_available", lambda port: len(popen_calls) >= 2)

    assert launcher._launch_chrome(9222) is True

    assert len(popen_calls) == 2
    assert r"--user-data-dir=C:\Users\shiva\AppData\Local\Google\Chrome\User Data" in popen_calls[0]
    assert f"--user-data-dir={tmp_path / 'ChromeDebugUserData'}" in popen_calls[1]


def test_launcher_waits_for_launch_in_progress_without_starting_another(monkeypatch):
    from agent.harness import launcher

    checks = iter([False, False, True])

    monkeypatch.setattr(launcher, "_launch_in_progress", True, raising=False)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(launcher, "is_chrome_debug_available", lambda port: next(checks, True))
    monkeypatch.setattr(
        launcher,
        "_launch_chrome",
        lambda port: (_ for _ in ()).throw(AssertionError("should not launch twice")),
        raising=False,
    )

    assert launcher.ensure_chrome_debug(9222) is True


def test_launcher_allows_only_one_startup_launch_attempt(monkeypatch):
    from agent.harness import launcher

    launch_calls = []

    monkeypatch.setattr(launcher, "_launch_in_progress", False, raising=False)
    monkeypatch.setattr(launcher, "_launch_succeeded", False, raising=False)
    monkeypatch.setattr(launcher, "_launch_attempted", False, raising=False)
    monkeypatch.setattr(launcher, "is_chrome_debug_available", lambda port: False)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(launcher, "_launch_chrome", lambda port: launch_calls.append(port) or False)

    assert launcher.ensure_chrome_debug(9222) is False
    assert launcher.ensure_chrome_debug(9222) is False
    assert launcher.ensure_chrome_debug(9222) is False
    assert launch_calls == [9222]


def test_browser_harness_keys_tabs_by_port_and_id():
    from agent.harness.browser import BrowserHarness

    assert BrowserHarness._tab_key(9222, "abc") == "9222:abc"


def test_tab_records_console_and_network_events():
    from agent.harness.tab import Tab

    tab = Tab(ws_url="ws://example", tab_id="1")
    tab._record_event(
        "Runtime.consoleAPICalled",
        {"args": [{"value": "hello"}, {"value": "world"}]},
    )
    tab._record_event(
        "Network.requestWillBeSent",
        {"requestId": "r1", "request": {"url": "https://example.test", "method": "GET"}},
    )

    assert tab._console_logs == ["hello world"]
    assert tab._network_log[0]["url"] == "https://example.test"
