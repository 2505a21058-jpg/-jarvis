"""
tests/test_readiness.py
"""

from unittest.mock import patch

from tools.readiness_check import _check_package, run_readiness_check


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
    ):
        result = run_readiness_check(memory=None)
    assert isinstance(result, dict)
    assert "ollama" in result


def test_run_no_crash_without_ollama():
    with patch("tools.readiness_check._check_ollama", return_value=(False, "Not running")), patch(
        "tools.readiness_check._check_model", return_value=(False, "Not pulled")
    ):
        result = run_readiness_check(memory=None)
    assert result["ollama"] is False
