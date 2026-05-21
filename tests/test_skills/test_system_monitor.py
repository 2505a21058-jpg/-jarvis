from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from skills.system_monitor import SystemMonitorSkill


@pytest.fixture
def skill():
    return SystemMonitorSkill()


def _make_mock_svmem(total=16_000_000_000, available=8_000_000_000, percent=50.0, used=8_000_000_000, free=8_000_000_000):
    mem = MagicMock()
    mem.total = total
    mem.available = available
    mem.percent = percent
    mem.used = used
    mem.free = free
    return mem


def _make_mock_sdiskusage(total=500_000_000_000, used=250_000_000_000, free=250_000_000_000, percent=50.0):
    disk = MagicMock()
    disk.total = total
    disk.used = used
    disk.free = free
    disk.percent = percent
    return disk


def _mock_psutil():
    psutil = MagicMock()
    psutil.cpu_percent.return_value = 45.0
    psutil.virtual_memory.return_value = _make_mock_svmem()
    psutil.disk_usage.return_value = _make_mock_sdiskusage()
    psutil.sensors_battery.return_value = None
    return psutil


def test_status_action_returns_stats(state, skill):
    with patch("skills.system_monitor._get_psutil", return_value=_mock_psutil()):
        result = skill.execute({"action": "status"}, state)
    assert result.success
    assert "CPU" in result.output


def test_unknown_action_returns_error(state, skill):
    result = skill.execute({"action": "invalid"}, state)
    assert not result.success


def test_default_action_is_status(state, skill):
    with patch("skills.system_monitor._get_psutil", return_value=_mock_psutil()):
        result = skill.execute({}, state)
    assert result.success
