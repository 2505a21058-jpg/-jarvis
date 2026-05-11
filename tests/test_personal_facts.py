"""
tests/test_personal_facts.py
"""

from memory.personal_facts import (
    extract_fact,
    format_facts_for_llm,
    get_all_facts,
    search_facts,
    store_fact,
)


def test_extract_like_statement():
    fact = extract_fact("I like Fanta")
    assert fact is not None
    assert "fanta" in fact.lower()


def test_extract_remember_statement():
    fact = extract_fact("remember that I prefer dark mode")
    assert fact is not None
    assert "dark mode" in fact.lower()


def test_extract_favorite_statement():
    fact = extract_fact("my favorite language is Rust")
    assert fact is not None
    assert "rust" in fact.lower()


def test_extract_returns_none_for_non_fact():
    assert extract_fact("open chrome") is None
    assert extract_fact("what is the weather") is None
    assert extract_fact("search for python") is None


def test_search_facts_returns_list(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "memory.personal_facts.FACTS_PATH",
        str(tmp_path / "personal_facts.jsonl"),
    )
    result = search_facts("what do I like")
    assert isinstance(result, list)


def test_format_facts_empty():
    result = format_facts_for_llm([])
    assert result == ""


def test_format_facts_non_empty():
    result = format_facts_for_llm(["I like Fanta", "I prefer dark mode"])
    assert "Fanta" in result
    assert "dark mode" in result
