"""
tests/test_readiness.py
"""

from unittest.mock import patch

from tools.readiness_check import _check_package, run_readiness_check


def test_chrome_harness_check_waits_for_launcher_guard(monkeypatch):
    from agent.harness import launcher
    from tools import readiness_check

    monkeypatch.setattr(launcher, "_CHROME_DEBUG_PORT", 9222)
    monkeypatch.setattr(launcher, "_CHROME_PROFILE", "Profile 3")
    monkeypatch.setattr(launcher, "ensure_chrome_debug", lambda: True)
    monkeypatch.setattr(
        launcher,
        "is_chrome_debug_available",
        lambda: (_ for _ in ()).throw(AssertionError("should wait through ensure_chrome_debug")),
    )

    ok, detail = readiness_check._check_chrome_harness()

    assert ok is True
    assert detail == "Port 9222 ready | Profile: Profile 3"


def test_check_package_installed():
    ok, msg = _check_package("os")
    assert ok is True


def test_check_package_missing():
    ok, msg = _check_package("nonexistent_package_xyz_123")
    assert ok is False
    assert "pip install" in msg


def test_run_returns_dict():
    with patch("tools.readiness_check._check_ollama", return_value=(True, "Running")), patch(
        "tools.readiness_check._check_model", return_value=(True, "Available")
    ), patch("tools.readiness_check._check_rawvision", return_value=("--", "Not initialized")), patch(
        "tools.readiness_check._check_hands", return_value=("--", "Not initialized")
    ), patch("tools.readiness_check._get_available_models", return_value=[], create=True), patch(
        "tools.readiness_check._check_playwright", return_value=True, create=True
    ), patch("tools.readiness_check._check_chrome_harness", return_value=(False, "Not ready"), create=True):
        result = run_readiness_check(memory=None)
    assert isinstance(result, dict)
    assert "ollama" in result


def test_run_no_crash_without_ollama():
    with patch("tools.readiness_check._check_ollama", return_value=(False, "Not running")), patch(
        "tools.readiness_check._check_model", return_value=(False, "Not pulled")
    ), patch("tools.readiness_check._check_rawvision", return_value=("--", "Not initialized")), patch(
        "tools.readiness_check._check_hands", return_value=("--", "Not initialized")
    ), patch("tools.readiness_check._get_available_models", return_value=[], create=True), patch(
        "tools.readiness_check._check_playwright", return_value=True, create=True
    ), patch("tools.readiness_check._check_chrome_harness", return_value=(False, "Not ready"), create=True):
        result = run_readiness_check(memory=None)
    assert result["ollama"] is False


def test_readiness_prints_powershell_env_guidance(capsys, monkeypatch):
    monkeypatch.delenv("JARVIS_VISION_VERIFY", raising=False)

    with patch("tools.readiness_check._check_ollama", return_value=(True, "Running")), patch(
        "tools.readiness_check._check_model", return_value=(True, "Available")
    ), patch("tools.readiness_check._check_rawvision", return_value=("--", "Not initialized")), patch(
        "tools.readiness_check._check_hands", return_value=("--", "Not initialized")
    ), patch("tools.readiness_check._get_available_models", return_value=[], create=True), patch(
        "tools.readiness_check._check_playwright", return_value=True, create=True
    ), patch("tools.readiness_check._check_chrome_harness", return_value=(False, "Not ready"), create=True):
        run_readiness_check(memory=None)

    output = capsys.readouterr().out
    assert "PowerShell: $env:JARVIS_VISION_VERIFY = \"true\"" in output
    assert "CMD:        set JARVIS_VISION_VERIFY=true" in output


def test_readiness_prints_rawvision_and_hands_status(capsys):
    with patch("tools.readiness_check._check_ollama", return_value=(True, "Running")), patch(
        "tools.readiness_check._check_model", return_value=(True, "Available")
    ), patch("tools.readiness_check._check_rawvision", return_value=("OK", "3 elements | layers: process_monitor,uia | 12ms")), patch(
        "tools.readiness_check._check_hands", return_value=("OK", "Terminal engine ready")
    ), patch("tools.readiness_check._get_available_models", return_value=[], create=True), patch(
        "tools.readiness_check._check_playwright", return_value=True, create=True
    ), patch("tools.readiness_check._check_chrome_harness", return_value=(False, "Not ready"), create=True):
        result = run_readiness_check(memory=None)

    output = capsys.readouterr().out
    assert "[OK] RawVision" in output
    assert "3 elements | layers: process_monitor,uia | 12ms" in output
    assert "[OK] Jarvis Hands" in output
    assert "Terminal engine ready" in output
    assert result["rawvision"] is True
    assert result["hands"] is True


def test_readiness_prints_model_roles_websocket_and_chrome(capsys, monkeypatch):
    monkeypatch.setenv("JARVIS_ACTION_MODEL", "gemma3:4b")
    monkeypatch.setenv("JARVIS_EMBED_MODEL", "nomic-embed-text")

    models = ["llama3.2:3b", "qwen3:8b", "gemma3:4b", "nomic-embed-text"]
    with patch("tools.readiness_check._check_ollama", return_value=(True, "Running")), patch(
        "tools.readiness_check._get_available_models", return_value=models, create=True
    ), patch("tools.readiness_check._check_rawvision", return_value=("--", "Not initialized")), patch(
        "tools.readiness_check._check_hands", return_value=("--", "Not initialized")
    ), patch("tools.readiness_check._check_playwright", return_value=True, create=True), patch(
        "tools.readiness_check._check_chrome_harness",
        return_value=(True, "Port 9222 ready | Profile: Profile 3"),
        create=True,
    ):
        result = run_readiness_check(memory=None)

    output = capsys.readouterr().out
    assert "[OK] Main model (reasoning)    qwen3:8b" in output
    assert "[OK] Action model (automation) gemma3:4b" in output
    assert "[OK] Embed model (memory)      nomic-embed-text" in output
    assert "[OK] Playwright (browser)      Available" in output
    assert "[OK] Chrome harness            Port 9222 ready | Profile: Profile 3" in output
    assert "WebSocket (websockets)" in output
    assert result["main_model"] is True
    assert result["action_model"] is True
