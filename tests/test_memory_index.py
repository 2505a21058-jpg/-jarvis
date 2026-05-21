from __future__ import annotations


def test_memory_index_searches_with_bm25_or_fallback():
    from memory.index import MemoryIndex

    idx = MemoryIndex()
    entries = [
        {"content": "opened chrome browser", "type": "experience", "tags": []},
        {"content": "searched for python tutorials", "type": "experience", "tags": []},
        {"content": "reminder set for 5 minutes", "type": "short_term", "tags": []},
    ]

    idx.build(entries)
    results = idx.search("open browser", limit=3)

    assert idx.size == 3
    assert results
    assert results[0][1]["content"] == "opened chrome browser"


def test_memory_index_incremental_add_is_searchable():
    from memory.index import MemoryIndex

    idx = MemoryIndex()
    idx.build([])
    idx.add({"content": "youtube automation workflow", "input": "open youtube", "tags": ["app:youtube"]})

    results = idx.search("youtube", limit=1)

    assert results[0][1]["content"] == "youtube automation workflow"
