# Jarvis internet access layer - Balanced Power + Speed
from .fetch import fetch_multiple, fetch_page
from .search import SearchResult, search
from .synthesize import synthesize
from .web_agent import deep_research, quick_answer, research

__all__ = [
    "search",
    "SearchResult",
    "research",
    "quick_answer",
    "deep_research",
    "fetch_page",
    "fetch_multiple",
    "synthesize",
]
