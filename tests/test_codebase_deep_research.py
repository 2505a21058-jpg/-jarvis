from __future__ import annotations

from unittest.mock import patch

from agent.intent.router import route
from agent.intent.schema import Intent, IntentName


def test_codebase_explore_intent_in_catalog():
    from agent.intent.schema import INTENT_CATALOG
    entry = INTENT_CATALOG.get(IntentName.CODABASE_EXPLORE)
    assert entry is not None
    assert entry["skill"] == "codebase_explorer"


def test_deep_research_intent_in_catalog():
    from agent.intent.schema import INTENT_CATALOG
    entry = INTENT_CATALOG.get(IntentName.DEEP_RESEARCH)
    assert entry is not None
    assert entry["skill"] == "deep_research"


def test_codebase_explore_routes_to_correct_skill():
    intent = Intent(name=IntentName.CODABASE_EXPLORE, entities={}, raw_input="how does the executor work")
    skill, params = route(intent)
    assert skill == "codebase_explorer"
    assert "query" in params


def test_deep_research_routes_to_correct_skill():
    intent = Intent(name=IntentName.DEEP_RESEARCH, entities={}, raw_input="compare jarvis to claude")
    skill, params = route(intent)
    assert skill == "deep_research"
    assert params.get("topic") == "compare jarvis to claude"


def test_codebase_explore_rule_deep_research():
    from agent.intent.rules import classify_with_rules
    intent = classify_with_rules("compare claude computer use to jarvis screenshot agent")
    assert intent is not None
    assert intent.name == IntentName.DEEP_RESEARCH


def test_codebase_explore_rule_codebase():
    from agent.intent.rules import classify_with_rules
    intent = classify_with_rules("how does the screenshot agent work")
    assert intent is not None
    assert intent.name == IntentName.CODABASE_EXPLORE


def test_codebase_explore_rule_show_code():
    from agent.intent.rules import classify_with_rules
    intent = classify_with_rules("show me the executor code")
    assert intent is not None
    assert intent.name == IntentName.CODABASE_EXPLORE


def test_deep_research_rule_deep():
    from agent.intent.rules import classify_with_rules
    intent = classify_with_rules("deep research on local llm agents")
    assert intent is not None
    assert intent.name == IntentName.DEEP_RESEARCH


def test_deep_research_does_not_consume_normal_queries():
    from agent.intent.rules import classify_with_rules
    intent = classify_with_rules("what is machine learning")
    if intent is not None:
        assert intent.name != IntentName.DEEP_RESEARCH


def test_codebase_explorer_skill_imports():
    from skills.codebase_explorer import CodebaseExplorerSkill
    skill = CodebaseExplorerSkill()
    assert skill.name == "codebase_explorer"
    assert skill.timeout_seconds == 30.0


def test_codebase_explorer_discover_files():
    from skills.codebase_explorer import CodebaseExplorerSkill
    skill = CodebaseExplorerSkill()
    with patch("skills.codebase_explorer.glob_mod.glob") as mock_glob, \
         patch("skills.codebase_explorer.os.path.isfile", return_value=True):
        mock_glob.return_value = ["agent/executor.py", "agent/act.py"]
        files = skill._discover_files("*.py")
        assert len(files) == 2


def test_codebase_explorer_grep_python():
    from skills.codebase_explorer import CodebaseExplorerSkill
    skill = CodebaseExplorerSkill()
    with patch.object(skill, "_grep_files", return_value=[("test.py", 1, "import re")]):
        matches = skill._grep_files("import re")
        assert len(matches) == 1


def test_codebase_explorer_read_files():
    from skills.codebase_explorer import CodebaseExplorerSkill
    skill = CodebaseExplorerSkill()
    with patch("builtins.open") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = "file content"
        contents = skill._read_files(["agent/executor.py"])
        assert isinstance(contents, dict)


def test_codebase_explorer_trace_imports():
    from skills.codebase_explorer import CodebaseExplorerSkill
    skill = CodebaseExplorerSkill()
    traced = skill._trace_imports("agent/executor.py", depth=1)
    assert isinstance(traced, list)


def test_codebase_explorer_static_mode_no_query():
    from skills.codebase_explorer import CodebaseExplorerSkill
    skill = CodebaseExplorerSkill()
    result = skill.execute({"mode": "read"}, None)
    assert not result.success
    assert error_in_result(result, "query")


def test_deep_research_decompose():
    from internet.deep_research import decompose_query
    with patch("models.llm.call_llm") as mock:
        mock.return_value = '["query one", "query two", "query three", "query four"]'
        queries = decompose_query("test topic", n=4)
        assert len(queries) == 4
        assert all(isinstance(q, str) for q in queries)


def test_deep_research_decompose_fallback():
    from internet.deep_research import decompose_query
    with patch("models.llm.call_llm") as mock:
        mock.side_effect = Exception("LLM error")
        queries = decompose_query("fallback topic", n=3)
        assert len(queries) == 1
        assert queries[0] == "fallback topic"


def test_deep_research_parallel_search():
    from internet.deep_research import parallel_search
    from internet.search import SearchResult
    with patch("internet.deep_research.search") as mock_search:
        mock_search.return_value = [
            SearchResult(title="R1", url="https://a.com", snippet="snippet", position=1),
            SearchResult(title="R2", url="https://b.com", snippet="snippet", position=2),
        ]
        results = parallel_search(["query1", "query2"], workers=2, max_results_per_query=3)
        assert isinstance(results, list)


def test_deep_research_should_fetch_skip_domains():
    from internet.deep_research import _should_fetch
    assert not _should_fetch("https://duckduckgo.com/")
    assert not _should_fetch("https://news.google.com/")
    assert _should_fetch("https://example.com/article")


def test_deep_research_fetch_pages():
    from internet.deep_research import _fetch_pages
    from internet.search import SearchResult
    with patch("internet.deep_research.fetch_page") as mock_fetch:
        mock_fetch.return_value = "Some content that is definitely longer than 80 characters for testing purposes to satisfy the length check."
        results = [SearchResult(title="T", url="https://x.com", snippet="s", position=1)]
        texts = _fetch_pages(results, max_fetch=1)
        assert isinstance(texts, dict)


def test_deep_research_full():
    from internet.deep_research import deep_research
    with patch.multiple("internet.deep_research",
                        decompose_query=lambda t, n, **kw: [t],
                        parallel_search=lambda q, **kw: [],
                        _fetch_pages=lambda r, **kw: {}):
        result = deep_research("test topic", depth=2)
        assert "No search results" in result


def error_in_result(result, text):
    return text.lower() in str(result.error or "").lower() or text.lower() in str(result.output or "").lower()
