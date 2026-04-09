import re
import webbrowser
from urllib.parse import quote, quote_plus
from memory.context import SESSION_CONTEXT


SEARCH_PROVIDERS = {
    "amazon": {
        "aliases": ("amazon",),
        "home": "https://www.amazon.com",
        "search": lambda query: f"https://www.amazon.com/s?k={quote_plus(query)}",
        "label": "Amazon",
    },
    "docs": {
        "aliases": ("google docs", "docs"),
        "home": "https://docs.google.com",
        "search": lambda query: f"https://docs.google.com/document/?q={quote_plus(query)}",
        "label": "Docs",
    },
    "drive": {
        "aliases": ("google drive", "drive"),
        "home": "https://drive.google.com",
        "search": lambda query: f"https://drive.google.com/drive/search?q={quote_plus(query)}",
        "label": "Drive",
    },
    "github": {
        "aliases": ("github", "gh"),
        "home": "https://github.com",
        "search": lambda query: f"https://github.com/search?q={quote_plus(query)}",
        "label": "GitHub",
    },
    "google": {
        "aliases": ("google",),
        "home": "https://www.google.com",
        "search": lambda query: f"https://www.google.com/search?q={quote_plus(query)}",
        "label": "Google",
    },
    "maps": {
        "aliases": ("google maps", "maps"),
        "home": "https://www.google.com/maps",
        "search": lambda query: f"https://www.google.com/maps/search/{quote(query)}",
        "label": "Google Maps",
    },
    "reddit": {
        "aliases": ("reddit",),
        "home": "https://www.reddit.com",
        "search": lambda query: f"https://www.reddit.com/search/?q={quote_plus(query)}",
        "label": "Reddit",
    },
    "spotify": {
        "aliases": ("spotify",),
        "home": "https://open.spotify.com",
        "search": lambda query: f"https://open.spotify.com/search/{quote(query)}",
        "label": "Spotify",
    },
    "wikipedia": {
        "aliases": ("wikipedia", "wiki"),
        "home": "https://en.wikipedia.org",
        "search": lambda query: f"https://en.wikipedia.org/w/index.php?search={quote_plus(query)}",
        "label": "Wikipedia",
    },
    "youtube": {
        "aliases": ("youtube", "yt"),
        "home": "https://www.youtube.com",
        "search": lambda query: f"https://www.youtube.com/results?search_query={quote_plus(query)}",
        "label": "YouTube",
    },
}

_ALIAS_TO_PROVIDER = {
    alias: provider
    for provider, config in SEARCH_PROVIDERS.items()
    for alias in config["aliases"]
}
_SORTED_ALIASES = sorted(_ALIAS_TO_PROVIDER, key=len, reverse=True)
_SEARCH_PREFIXES = (
    "search for ",
    "search ",
    "find on ",
    "find ",
    "look up ",
    "browse for ",
    "browse ",
    "open ",
)


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned


def _normalize_lower(text: str) -> str:
    return _normalize_text(text).lower()


def _strip_prefix(query: str) -> tuple[str, str]:
    lowered = _normalize_lower(query)
    text = _normalize_text(query)

    for prefix in _SEARCH_PREFIXES:
        if lowered.startswith(prefix):
            return prefix.strip(), text[len(prefix):].strip()
    return "", text.strip()


def _looks_like_url(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered.startswith(("http://", "https://")) or bool(
        re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?", lowered)
    )


def _to_url(text: str) -> str:
    cleaned = text.strip()
    if cleaned.lower().startswith(("http://", "https://")):
        return cleaned
    return f"https://{cleaned}"


def resolve_context_app(context_app: str) -> str:
    lowered = _normalize_lower(context_app)
    if any(token in lowered for token in ("chrome", "browser")):
        return "google"
    for alias in _SORTED_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return _ALIAS_TO_PROVIDER[alias]
    return ""


def _extract_provider(query: str) -> tuple[str, str]:
    lowered = _normalize_lower(query)
    for alias in _SORTED_ALIASES:
        if lowered == alias:
            return _ALIAS_TO_PROVIDER[alias], ""
        if lowered.startswith(f"{alias} "):
            remainder = query[len(alias):].strip()
            remainder = re.sub(r"^(?:for|on)\s+", "", remainder, flags=re.IGNORECASE).strip()
            return _ALIAS_TO_PROVIDER[alias], remainder
    return "", query.strip()


def _get_context_provider(context_app: str = "") -> str:
    active_context = context_app or SESSION_CONTEXT.get_app()
    return resolve_context_app(active_context)


def resolve_search_target(query: str, context_app: str = "") -> dict:
    original = _normalize_text(query)
    if not original:
        return {"type": "url", "value": "https://duckduckgo.com", "provider": "", "query": "", "url": "https://duckduckgo.com", "source": "default"}

    if _looks_like_url(original):
        url = _to_url(original)
        return {"type": "url", "value": url, "provider": "", "query": "", "url": url, "source": "direct_url"}

    action, stripped = _strip_prefix(original)
    provider, remainder = _extract_provider(stripped)

    if provider:
        if remainder:
            url = SEARCH_PROVIDERS[provider]["search"](remainder)
            return {"type": "provider_search", "value": remainder, "provider": provider, "query": remainder, "url": url, "source": "explicit_provider"}
        url = SEARCH_PROVIDERS[provider]["home"]
        return {"type": "provider_home", "value": url, "provider": provider, "query": "", "url": url, "source": "explicit_provider"}

    context_provider = _get_context_provider(context_app)
    search_query = stripped or original
    if context_provider and search_query:
        url = SEARCH_PROVIDERS[context_provider]["search"](search_query)
        return {"type": "provider_search", "value": search_query, "provider": context_provider, "query": search_query, "url": url, "source": "context_provider"}

    web_query = search_query
    url = f"https://duckduckgo.com/?q={quote_plus(web_query)}"
    return {"type": "web_search", "value": web_query, "provider": "", "query": web_query, "url": url, "source": "default"}


def execute_search(resolved: dict) -> str:
    search_type = str(resolved.get("type", "")).strip().lower()
    url = str(resolved.get("url", "")).strip()
    provider = str(resolved.get("provider", "")).strip()
    query = str(resolved.get("query", "")).strip()
    source = str(resolved.get("source", "")).strip().lower()

    if not url:
        url = "https://duckduckgo.com"
        search_type = "url"

    webbrowser.open_new_tab(url)

    if search_type == "provider_home" and provider:
        SESSION_CONTEXT.set_app(provider)
        SESSION_CONTEXT.last_action = f"open:{provider}"
        return f"Opened {SEARCH_PROVIDERS[provider]['label']}."
    if search_type == "provider_search" and provider:
        if source == "explicit_provider":
            SESSION_CONTEXT.set_app(provider)
        SESSION_CONTEXT.last_action = f"search:{provider}"
        return f"Searched {SEARCH_PROVIDERS[provider]['label']} for {query}."
    SESSION_CONTEXT.last_action = "search:web"
    if search_type == "url":
        return f"Opened {url}."
    return f"Searched for {query or url}."
