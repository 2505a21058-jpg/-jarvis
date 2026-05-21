from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def skill():
    from skills.send_email import SendEmailSkill
    return SendEmailSkill()


def test_send_email_sends_via_smtp(state, skill):
    params = {"to": "test@example.com", "subject": "Test", "body": "Hello"}
    with patch.dict("os.environ", {
        "JARVIS_SMTP_HOST": "smtp.example.com",
        "JARVIS_SMTP_PORT": "587",
        "JARVIS_SMTP_USER": "user@example.com",
        "JARVIS_SMTP_PASS": "secret",
    }, clear=False):
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            result = skill.execute(params, state)
    assert result.success
    instance.sendmail.assert_called_once()


def test_send_email_requires_recipient(state, skill):
    with patch.dict("os.environ", {"JARVIS_SMTP_HOST": "smtp.com", "JARVIS_SMTP_USER": "u", "JARVIS_SMTP_PASS": "p"}, clear=False):
        result = skill.execute({"subject": "Test", "body": "Hello"}, state)
    assert not result.success
    assert "recipient" in result.error.lower()


def test_send_email_requires_body(state, skill):
    with patch.dict("os.environ", {"JARVIS_SMTP_HOST": "smtp.com", "JARVIS_SMTP_USER": "u", "JARVIS_SMTP_PASS": "p"}, clear=False):
        result = skill.execute({"to": "a@b.com", "subject": "Test"}, state)
    assert not result.success
    assert "body" in result.error.lower()


def test_send_email_without_smtp_config_returns_error(state, skill):
    result = skill.execute({"to": "test@example.com", "subject": "Test", "body": "Hello"}, state)
    assert not result.success
    assert "SMTP not configured" in result.error
