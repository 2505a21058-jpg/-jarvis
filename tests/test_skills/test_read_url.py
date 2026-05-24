"""Tests for ReadUrlSkill — fetch and summarize any URL."""

from __future__ import annotations

from unittest.mock import patch

from skills.base import SkillResult
from skills.read_url import ReadUrlSkill


def _skill():
    return ReadUrlSkill()


def test_no_url_returns_error():
    result = _skill().execute({}, None)
    assert not result.success
    assert "provide a URL" in result.error


def test_fetch_failure_returns_error():
    with patch("internet.fetch.fetch_page", return_value=None):
        result = _skill().execute({"url": "https://example.com"}, None)
    assert not result.success
    assert "Could not read content" in result.error


def test_short_content_returns_error():
    with patch("internet.fetch.fetch_page", return_value="short"):
        result = _skill().execute({"url": "https://example.com"}, None)
    assert not result.success


def test_successful_fetch_and_summary():
    mock_content = "This is a long article content with lots of useful information about a topic." * 20
    with patch("internet.fetch.fetch_page", return_value=mock_content):
        with patch("models.llm.call_llm") as mock_llm:
            mock_llm.return_value = "This page discusses an interesting topic with key takeaways."
            result = _skill().execute({"url": "https://example.com/article"}, None)

    assert result.success
    assert "Summary of" in result.output
    assert "interesting topic" in result.output
    assert "example.com" in result.output


def test_llm_failure_falls_back_to_raw_content():
    mock_content = "Raw page content that gets shown directly." * 50
    with patch("internet.fetch.fetch_page", return_value=mock_content):
        with patch("models.llm.call_llm") as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM unavailable")
            result = _skill().execute({"url": "https://example.com"}, None)

    assert result.success
    assert "Content from" in result.output
    assert "Raw page content" in result.output


def test_url_normalization_adds_https():
    with patch("internet.fetch.fetch_page", return_value="Content " * 30):
        with patch("models.llm.call_llm", return_value="Summary text."):
            result = _skill().execute({"url": "example.com"}, None)
    assert result.success


def test_topic_param_used_as_url():
    with patch("internet.fetch.fetch_page", return_value="Content " * 30):
        with patch("models.llm.call_llm", return_value="Summary."):
            result = _skill().execute({"topic": "https://example.org/page"}, None)
    assert result.success
