from __future__ import annotations

from agent.intent.router import route
from agent.intent.schema import Intent, IntentName
from skills.base import SkillResult


def test_duckduckgo_html_parser_extracts_ranked_results():
    from internet.search import _parse_ddgo_html

    html = """
    <div class="result__body">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpython&amp;rut=abc">Python &amp; News</a>
      <a class="result__snippet">Latest <b>Python</b> release info.</a>
    </div></div></div>
    <div class="result__body">
      <a class="result__a" href="https://duckduckgo.com/y.js">internal</a>
      <a class="result__snippet">skip this</a>
    </div></div></div>
    <div class="result__body">
      <a class="result__a" href="https://example.org/docs">Docs</a>
      <a class="result__snippet">Documentation snippet.</a>
    </div></div></div>
    """

    results = _parse_ddgo_html(html, max_results=5)

    assert [result.url for result in results] == ["https://example.com/python", "https://example.org/docs"]
    assert results[0].position == 1
    assert results[0].title == "Python & News"
    assert results[0].snippet == "Latest Python release info."


def test_fetch_fallback_extracts_clean_text():
    from internet.fetch import _extract_text

    html = """
    <html>
      <head><style>.hidden{display:none}</style><script>alert('x')</script></head>
      <body><main><h1>Jarvis Web</h1><p>This is useful readable article content for extraction with enough length to pass quality thresholds.</p></main></body>
    </html>
    """

    text = _extract_text(html, "https://example.com/article")

    assert text is not None
    assert "Jarvis Web" in text
    assert "useful readable article content" in text
    assert "alert" not in text


def test_quick_answer_searches_without_fetching(monkeypatch):
    from internet.search import SearchResult
    import internet.web_agent as web_agent

    calls = []
    sample_results = [SearchResult("Title", "https://example.com", "Snippet", 1)]
    monkeypatch.setattr(web_agent, "search", lambda query, max_results: sample_results)
    monkeypatch.setattr(web_agent, "fetch_multiple", lambda urls, max_workers=3: calls.append(urls) or {})
    monkeypatch.setattr(web_agent, "synthesize", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("quick mode should not call LLM synthesis")))

    response = web_agent.quick_answer("current python version")

    assert "Quick search results for 'current python version'" in response
    assert "[1] Title" in response
    assert "Source: https://example.com" in response
    assert calls == []


def test_normal_research_fetches_top_three(monkeypatch):
    from internet.search import SearchResult
    import internet.web_agent as web_agent

    sample_results = [
        SearchResult(f"Title {index}", f"https://example.com/{index}", f"Snippet {index}", index)
        for index in range(1, 6)
    ]
    fetched = {}
    monkeypatch.setattr(web_agent, "search", lambda query, max_results: sample_results)

    def fake_fetch(urls, max_workers=3):
        fetched["urls"] = urls
        fetched["workers"] = max_workers
        return {url: f"Text for {url}" for url in urls}

    monkeypatch.setattr(web_agent, "fetch_multiple", fake_fetch)
    monkeypatch.setattr(web_agent, "synthesize", lambda query, results, page_texts, **kw: "answer")

    assert web_agent.research("spacex recently", depth="normal") == "answer"
    assert fetched["urls"] == [f"https://example.com/{index}" for index in range(1, 4)]
    assert fetched["workers"] == 3


def test_synthesize_uses_sources_and_citations(monkeypatch):
    from internet.search import SearchResult
    from internet.synthesize import synthesize

    captured = {}

    def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return "Answer with [1]."

    monkeypatch.setattr("models.llm.call_llm", fake_call_llm)
    monkeypatch.setattr(
        "models.llm.run_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("synthesis should use call_llm")),
    )
    results = [SearchResult("Example", "https://example.com", "Short snippet fallback text.", 1)]

    response = synthesize("what happened", results, {"https://example.com": "Detailed source text " * 20})

    assert response == "Answer with [1]."
    assert captured["timeout"] == 30
    assert "Question: what happened" in captured["user"]
    assert "[1] Example" in captured["user"]
    assert "Cite sources" in captured["system"]


def test_synthesize_falls_back_to_search_results(monkeypatch):
    from internet.search import SearchResult
    from internet.synthesize import synthesize

    def broken_call_llm(*args, **kwargs):
        raise RuntimeError("model offline")

    monkeypatch.setattr("models.llm.call_llm", broken_call_llm)
    results = [
        SearchResult(
            "Example",
            "https://example.com",
            "Useful snippet with enough detail to be considered a usable source for fallback synthesis.",
            1,
        )
    ]

    response = synthesize("query", results, {})

    assert "Quick search results" in response
    assert "Useful snippet with enough detail" in response
    assert "https://example.com" in response


def test_web_research_skills_return_skill_results(monkeypatch):
    from skills.web_research import QuickSearchSkill, WebResearchSkill

    monkeypatch.setattr("internet.web_agent.quick_answer", lambda query: f"quick:{query}")
    monkeypatch.setattr("internet.web_agent.research", lambda query, depth="normal": f"{depth}:{query}")

    summary = WebResearchSkill().execute({"topic": "python", "depth": "deep"}, None)
    quick = QuickSearchSkill().execute({"query": "python"}, None)

    assert isinstance(summary, SkillResult)
    assert summary.success is True
    assert summary.output == "deep:python"
    assert quick.success is True
    assert quick.output == "quick:python"


def test_router_maps_web_search_to_quick_web_skill():
    intent = Intent(
        name=IntentName.WEB_SEARCH,
        raw_input="search current python version",
    )

    skill_name, params = route(intent)

    assert skill_name == "web_search"
    assert params == {}
