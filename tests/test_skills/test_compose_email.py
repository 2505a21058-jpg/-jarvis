from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.compose_email import ComposeEmailSkill


@pytest.fixture
def skill():
    return ComposeEmailSkill()


def test_sends_via_gmail_browser(state, skill):
    with patch("webbrowser.open") as mock_web:
        result = skill.execute({"to": "a@b.com", "subject": "Hello", "body": "Test body"}, state)
    assert result.success
    assert "Gmail compose" in result.output
    mock_web.assert_called_once()
    url = mock_web.call_args[0][0]
    assert "mail.google.com" in url


def test_requires_valid_recipient(state, skill):
    result = skill.execute({"to": "invalid"}, state)
    assert not result.success
    assert "valid email" in result.error.lower()


def test_no_recipient_returns_error(state, skill):
    result = skill.execute({"to": ""}, state)
    assert not result.success
    assert "No recipient" in result.error


def test_generates_subject_from_body(state, skill):
    with patch("webbrowser.open") as mock_web:
        result = skill.execute({"to": "a@b.com", "body": "Meeting tomorrow"}, state)
    assert result.success
    url = mock_web.call_args[0][0]
    assert "su=Meeting" in url


def test_sends_via_smtp_when_configured(state, skill):
    with patch.dict("os.environ", {"JARVIS_SMTP_HOST": "smtp.com", "JARVIS_SMTP_USER": "u", "JARVIS_SMTP_PASS": "p"}, clear=False):
        with patch("smtplib.SMTP") as mock_smtp:
            result = skill.execute({"to": "a@b.com", "body": "Test"}, state)
    assert result.success
    assert "Email sent" in result.output
