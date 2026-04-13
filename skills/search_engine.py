import re
import webbrowser
from urllib.parse import quote
from memory.context import SESSION_CONTEXT
from .browser_control import is_browser_context, open_url_in_browser


def _encode_query(query: str) -> str:
    return quote(str(query).strip(), safe="")


SEARCH_PROVIDERS = {
    "amazon": {
        "aliases": ("amazon",),
        "home": "https://www.amazon.com",
        "search": lambda query: f"https://www.amazon.com/s?k={_encode_query(query)}",
        "label": "Amazon",
    },
    "docs": {
        "aliases": ("google docs", "docs"),
        "home": "https://docs.google.com",
        "search": lambda query: f"https://docs.google.com/document/?q={_encode_query(query)}",
        "label": "Docs",
    },
    "drive": {
        "aliases": ("google drive", "drive"),
        "home": "https://drive.google.com",
        "search": lambda query: f"https://drive.google.com/drive/search?q={_encode_query(query)}",
        "label": "Drive",
    },
    "github": {
        "aliases": ("github", "gh"),
        "home": "https://github.com",
        "search": lambda query: f"https://github.com/search?q={_encode_query(query)}",
        "label": "GitHub",
    },
    "google": {
        "aliases": ("google",),
        "home": "https://www.google.com",
        "search": lambda query: f"https://www.google.com/search?q={_encode_query(query)}",
        "label": "Google",
    },
    "maps": {
        "aliases": ("google maps", "maps"),
        "home": "https://www.google.com/maps",
        "search": lambda query: f"https://www.google.com/maps/search/{_encode_query(query)}",
        "label": "Google Maps",
    },
    "reddit": {
        "aliases": ("reddit",),
        "home": "https://www.reddit.com",
        "search": lambda query: f"https://www.reddit.com/search/?q={_encode_query(query)}",
        "label": "Reddit",
    },
    "spotify": {
        "aliases": ("spotify",),
        "home": "https://open.spotify.com",
        "search": lambda query: f"https://open.spotify.com/search/{_encode_query(query)}",
        "label": "Spotify",
    },
    "wikipedia": {
        "aliases": ("wikipedia", "wiki"),
        "home": "https://en.wikipedia.org",
        "search": lambda query: f"https://en.wikipedia.org/w/index.php?search={_encode_query(query)}",
        "label": "Wikipedia",
    },
    "youtube": {
        "aliases": ("youtube", "yt"),
        "home": "https://www.youtube.com",
        "search": lambda query: f"https://www.youtube.com/results?search_query={_encode_query(query)}",
        "label": "YouTube",
    },
}

CONTEXT_SEARCH_PROVIDERS = {
    "youtube": "youtube",
    "yt": "youtube",
    "chrome": "google",
    "browser": "google",
    "google": "google",
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
    for alias, provider in CONTEXT_SEARCH_PROVIDERS.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return provider
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
    if context_app:
        provider = resolve_context_app(context_app)
        if provider:
            return provider

    active_platform = SESSION_CONTEXT.get_platform()
    if active_platform in SEARCH_PROVIDERS:
        return active_platform

    return resolve_context_app(SESSION_CONTEXT.get_app())


def _open_search_url(url: str) -> str:
    active_app = SESSION_CONTEXT.get_app()
    if is_browser_context(active_app):
        success, _error = open_url_in_browser(url, app_name=active_app)
        if success:
            return "browser_control"

    webbrowser.open_new_tab(url)
    return "webbrowser"


def _mark_browser_context(provider: str = ""):
    if provider:
        if not is_browser_context(SESSION_CONTEXT.get_app()):
            SESSION_CONTEXT.set_app("browser", platform=provider)
        else:
            SESSION_CONTEXT.set_platform(provider)


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
    url = f"https://duckduckgo.com/?q={_encode_query(web_query)}"
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

    open_method = _open_search_url(url)

    if search_type == "provider_home" and provider:
        _mark_browser_context(provider)
        SESSION_CONTEXT.last_action = f"open:{provider}"
        return f"Opened {SEARCH_PROVIDERS[provider]['label']}."
    if search_type == "provider_search" and provider:
        if source in {"explicit_provider", "context_provider"}:
            _mark_browser_context(provider)
        SESSION_CONTEXT.last_action = f"search:{provider}"
        return f"Searched {SEARCH_PROVIDERS[provider]['label']} for {query}."
    SESSION_CONTEXT.last_action = "search:web"
    if open_method == "browser_control":
        SESSION_CONTEXT.last_action = "search:browser"
    if search_type == "url":
        return f"Opened {url}."
    return f"Searched for {query or url}."
