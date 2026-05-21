from __future__ import annotations

import time
from datetime import datetime, timedelta

from memory.core import (
    auto_tag,
    compute_importance,
    get_stats,
    prune_by_ttl,
    prune_stale_memories,
    retrieve_bm25,
    retrieve_relevant,
)


def test_store_and_recent(memory):
    memory.store(content="hello world test entry", tags=["test"])
    recent = memory.recent(n=1)
    assert len(recent) == 1
    assert recent[0]["content"] == "hello world test entry"


def test_store_types(memory):
    memory.store(content="recent", memory_type="recent")
    memory.store(content="long", memory_type="long_term")
    memory.store(content="exp", memory_type="experience")
    assert len(memory._recent_index._entries) == 1
    assert len(memory._long_term_index._entries) == 1
    assert len(memory._experience_index._entries) == 1


def test_retrieve_relevant_first(memory):
    memory.store(content="cats are furry animals", memory_type="long_term")
    memory.store(content="python is a programming language", memory_type="long_term")
    memory.store(content="dogs are loyal pets", memory_type="long_term")
    results = memory.retrieve("python programming", mode="deep", limit=3)
    assert results[0]["content"] == "python is a programming language"


def test_retrieve_tags(memory):
    memory.store(content="learned skill entry", tags=["learned_skill", "test_skill"])
    results = memory.retrieve("learned_skill test_skill", mode="tags", limit=5)
    assert len(results) > 0


def test_retrieve_limit(memory):
    for i in range(10):
        memory.store(content=f"entry {i} about testing things carefully", memory_type="long_term")
    results = memory.retrieve("testing", mode="deep", limit=3)
    assert len(results) <= 3


def test_retrieve_deep(memory):
    memory.store(content="recent python entry", memory_type="recent")
    memory.store(content="long term python history", memory_type="long_term")
    results = memory.retrieve("python", mode="deep", limit=10)
    contents = [result["content"] for result in results]
    assert any("recent" in content for content in contents)
    assert any("long term" in content for content in contents)


def test_prune_experiences(memory):
    for i in range(20):
        memory.store(content=f"experience {i} test data", memory_type="experience")
    memory.prune_experiences(max_entries=10)
    assert len(memory._experience_index._entries) == 10


def test_promote_to_long_term(memory):
    entry = {
        "content": "important experience " + "x" * 60,
        "tags": ["experience"],
        "metadata": {"importance": 0.9},
        "timestamp": time.time(),
    }
    memory.promote_to_long_term(entry)
    assert len(memory._long_term_index._entries) == 1


def test_promote_deduplication(memory):
    entry = {
        "content": "duplicate content test " + "x" * 60,
        "tags": [],
        "metadata": {},
        "timestamp": time.time(),
    }
    memory.promote_to_long_term(entry)
    memory.promote_to_long_term(entry)
    assert len(memory._long_term_index._entries) == 1


def test_retrieve_relevant_tfidf_ranks_specific_memory_first():
    entries = [
        {"content": "opened paint and drew a blue circle", "type": "experience"},
        {"content": "checked cpu usage and ram pressure", "type": "experience"},
        {"content": "booked a train ticket to hyderabad", "type": "long_term"},
    ]

    results = retrieve_relevant("check cpu", entries, limit=3)

    assert results[0]["content"] == "checked cpu usage and ram pressure"


def test_retrieve_relevant_respects_context_budget():
    entries = [
        {"content": "cpu " + ("very long diagnostic notes " * 80), "type": "experience"},
        {"content": "cpu short note", "type": "experience"},
    ]

    results = retrieve_relevant("cpu", entries, limit=2, budget_tokens=10)

    assert len(results) == 1
    assert results[0]["content"] == "cpu short note"


def test_retrieve_relevant_weights_experiences_above_short_term():
    older = (datetime.now() - timedelta(days=3)).isoformat()
    entries = [
        {"content": "cpu temperature was checked", "type": "short_term", "timestamp": older},
        {"content": "cpu temperature was checked", "type": "experience", "timestamp": older},
    ]

    results = retrieve_relevant("cpu temperature", entries, limit=2)

    assert results[0]["type"] == "experience"


def test_fast_retrieve_filters_irrelevant_recent_entries(memory):
    memory.store(content="gpu telemetry was checked", memory_type="recent")
    memory.store(content="made a pasta recipe", memory_type="recent")

    results = memory.retrieve("gpu telemetry", mode="fast", limit=5)

    assert [entry["content"] for entry in results] == ["gpu telemetry was checked"]


def test_prune_stale_memories_removes_old_low_value_entries():
    old = (datetime.now() - timedelta(days=45)).isoformat()
    recent = datetime.now().isoformat()
    entries = [
        {"content": "old forgotten note", "timestamp": old, "score": 0.0, "access_count": 0},
        {"content": "old recalled note", "timestamp": old, "score": 0.0, "access_count": 2},
        {"content": "recent note", "timestamp": recent, "score": 0.0, "access_count": 0},
    ]

    kept, removed = prune_stale_memories(entries)

    assert removed == 1
    assert [entry["content"] for entry in kept] == ["old recalled note", "recent note"]


def test_get_stats_reports_memory_index_counts(memory):
    memory.store(content="recent note", memory_type="recent")
    memory.store(content="long note", memory_type="long_term")
    memory.store(content="experience note", memory_type="experience")

    stats = get_stats(memory)

    assert stats["recent"] == 1
    assert stats["long_term"] == 1
    assert stats["experience"] == 1
    assert stats["total"] == 3


def test_auto_tag_extracts_common_entities():
    tags = auto_tag("Open Chrome and search https://example.com in 5 minutes")

    assert "web" in tags
    assert "app:chrome" in tags
    assert "action:open" in tags
    assert "action:search" in tags
    assert "time_sensitive" in tags


def test_compute_importance_boosts_access_and_type():
    now = datetime.now().isoformat()
    low = {"content": "low", "type": "short_term", "timestamp": now, "access_count": 0}
    high = {
        "content": "high",
        "type": "experience",
        "timestamp": now,
        "access_count": 10,
        "metadata": {"eval_confidence": 0.95},
    }

    assert compute_importance(high) > compute_importance(low)


def test_retrieve_bm25_reranks_by_importance(memory):
    entries = [
        {
            "content": "chrome browser automation",
            "type": "short_term",
            "timestamp": datetime.now().isoformat(),
            "access_count": 0,
            "tags": [],
        },
        {
            "content": "chrome browser automation",
            "type": "experience",
            "timestamp": datetime.now().isoformat(),
            "access_count": 12,
            "tags": [],
        },
    ]
    memory._bm25_index.build(entries)

    results = retrieve_bm25("chrome browser", memory._bm25_index, entries, limit=2)

    assert results[0]["type"] == "experience"


def test_memory_add_auto_tags_and_updates_bm25_index(memory):
    entry = memory.add(
        "open chrome and search https://example.com",
        memory_type="experience",
        tags=["manual"],
    )

    assert "manual" in entry["tags"]
    assert "app:chrome" in entry["tags"]
    assert "action:search" in entry["tags"]
    assert memory._bm25_index.search("chrome example", limit=1)


def test_memory_retrieve_uses_bm25_index(memory):
    memory.add("opened chrome browser", memory_type="experience")
    memory.add("searched for python tutorials", memory_type="experience")

    results = memory.retrieve("open browser", mode="deep", limit=2)

    assert results[0]["content"] == "opened chrome browser"


def test_prune_by_ttl_removes_only_old_low_importance_entries():
    old = (datetime.now() - timedelta(days=90)).isoformat()
    recent = datetime.now().isoformat()
    entries = [
        {"content": "old low", "timestamp": old, "type": "short_term", "access_count": 0},
        {"content": "old accessed", "timestamp": old, "type": "experience", "access_count": 20},
        {"content": "recent low", "timestamp": recent, "type": "short_term", "access_count": 0},
    ]

    kept, removed = prune_by_ttl(entries)

    assert removed == 1
    assert [entry["content"] for entry in kept] == ["old accessed", "recent low"]


def test_memory_prune_rewrites_indexes(memory):
    old = (datetime.now() - timedelta(days=90)).isoformat()
    memory.store({"content": "old low", "timestamp": old, "type": "short_term", "access_count": 0})
    memory.add("recent chrome memory", memory_type="long_term")

    removed = memory.prune()

    assert removed == 1
    assert all(entry.get("content") != "old low" for entry in memory._get_all_entries())
    assert memory._bm25_index.search("recent chrome", limit=1)
