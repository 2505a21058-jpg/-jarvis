from __future__ import annotations

import time


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
