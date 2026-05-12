"""
skills/web_summary.py

Searches the web for a topic then summarizes the results using LLM.
Handles "summarise X", "what is X", "tell me about X" commands.

Does not use browser automation. It fetches search result text with
direct HTTP requests and summarizes via the local LLM.
"""

import logging
from html.parser import HTMLParser
from urllib.parse import quote_plus

from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.web_summary")

_SEARCH_URL = "https://www.google.com/search?q={query}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
_MAX_CONTENT_CHARS = 3000


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.skip_tags = {"script", "style", "nav", "header", "footer"}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        stripped = data.strip()
        if len(stripped) > 20:
            self.text_parts.append(stripped)


def _fetch_search_snippet(query: str) -> str:
    """
    Fetch Google search results page and extract text snippets.
    Returns raw text content for LLM summarization.
    """
    try:
        import requests

        url = _SEARCH_URL.format(query=quote_plus(query))
        response = requests.get(url, headers=_HEADERS, timeout=8)

        parser = _TextExtractor()
        parser.feed(response.text)

        content = " ".join(parser.text_parts)
        return content[:_MAX_CONTENT_CHARS]

    except Exception as exc:
        logger.error("Web fetch failed: %s", exc)
        return ""


class WebSummarySkill(SkillBase):
    name = "web_summary"
    description = "Searches the web and summarizes information about a topic"
    timeout_seconds = 20.0

    def execute(self, params: dict, state) -> SkillResult:
        topic = params.get("topic", params.get("query", "")).strip()

        if not topic:
            return SkillResult(
                success=False,
                output=None,
                error="No topic provided to summarize",
                skill_name=self.name,
            )

        logger.info("Web summary requested for: %s", topic)
        content = _fetch_search_snippet(topic)

        if not content:
            content = f"Topic: {topic}\nNote: Web fetch failed, using model knowledge only."

        try:
            from models.llm import call_llm

            summary = call_llm(
                system=(
                    "You are a research assistant. "
                    "Summarize the following web search content about the given topic. "
                    "Be factual, concise, and focus on the most important information. "
                    "Write 3-5 clear sentences. No bullet points unless essential."
                ),
                user=f"Topic: {topic}\n\nSearch results content:\n{content}",
                temperature=0.3,
                max_tokens=400,
            )
            return SkillResult(
                success=True,
                output=f"Summary of '{topic}':\n\n{summary.strip()}",
                skill_name=self.name,
            )
        except Exception as exc:
            logger.error("LLM summarization failed: %s", exc)
            return SkillResult(
                success=False,
                output=None,
                error=f"Could not summarize: {exc}",
                skill_name=self.name,
            )
