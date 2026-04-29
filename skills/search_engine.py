from __future__ import annotations

import re
import webbrowser
from typing import Any
from urllib.parse import quote
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


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    getter = getattr(state, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(state, key, default)


def _state_set(state: Any, key: str, value: Any) -> None:
    if state is None:
        return
    if hasattr(state, key):
        setattr(state, key, value)
    elif isinstance(state, dict):
        state[key] = value


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


def _get_context_provider(context_app: str = "", state: Any = None) -> str:
    if context_app:
        provider = resolve_context_app(context_app)
        if provider:
            return provider

    active_platform = str(_state_get(state, "active_platform", "") or "").strip().lower()
    if active_platform in SEARCH_PROVIDERS:
        return active_platform

    configured_engine = str(_state_get(state, "search_engine", "") or "").strip().lower()
    if configured_engine in SEARCH_PROVIDERS:
        return configured_engine

    return resolve_context_app(str(_state_get(state, "active_app", "") or ""))


def _open_search_url(url: str, state: Any = None) -> str:
    active_app = str(_state_get(state, "active_app", "") or "")
    if is_browser_context(active_app):
        success, _error = open_url_in_browser(url, app_name=active_app, state=state)
        if success:
            return "browser_control"

    webbrowser.open_new_tab(url)
    _state_set(state, "browser_url", url)
    return "webbrowser"


def _mark_browser_context(provider: str = "", state: Any = None):
    if provider:
        active_app = str(_state_get(state, "active_app", "") or "")
        if not is_browser_context(active_app):
            if hasattr(state, "set_active_app"):
                state.set_active_app("browser")
            else:
                _state_set(state, "active_app", "browser")
                _state_set(state, "active_platform", "browser")
            _state_set(state, "active_platform", provider)
        else:
            _state_set(state, "active_platform", provider)
        if hasattr(state, "set_search_engine"):
            state.set_search_engine(provider)
        else:
            _state_set(state, "search_engine", provider)


def resolve_search_target(query: str, context_app: str = "", state: Any = None) -> dict:
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

    context_provider = _get_context_provider(context_app, state=state)
    search_query = stripped or original
    if context_provider and search_query:
        url = SEARCH_PROVIDERS[context_provider]["search"](search_query)
        return {"type": "provider_search", "value": search_query, "provider": context_provider, "query": search_query, "url": url, "source": "context_provider"}

    web_query = search_query
    url = f"https://duckduckgo.com/?q={_encode_query(web_query)}"
    return {"type": "web_search", "value": web_query, "provider": "", "query": web_query, "url": url, "source": "default"}


def execute_search(resolved: dict, state: Any = None) -> str:
    search_type = str(resolved.get("type", "")).strip().lower()
    url = str(resolved.get("url", "")).strip()
    provider = str(resolved.get("provider", "")).strip()
    query = str(resolved.get("query", "")).strip()
    source = str(resolved.get("source", "")).strip().lower()

    if not url:
        url = "https://duckduckgo.com"
        search_type = "url"

    open_method = _open_search_url(url, state=state)

    if search_type == "provider_home" and provider:
        _mark_browser_context(provider, state=state)
        _state_set(state, "last_action", f"open:{provider}")
        return f"Opened {SEARCH_PROVIDERS[provider]['label']}."
    if search_type == "provider_search" and provider:
        if source in {"explicit_provider", "context_provider"}:
            _mark_browser_context(provider, state=state)
        _state_set(state, "last_action", f"search:{provider}")
        return f"Searched {SEARCH_PROVIDERS[provider]['label']} for {query}."
    _state_set(state, "last_action", "search:web")
    if open_method == "browser_control":
        _state_set(state, "last_action", "search:browser")
    if search_type == "url":
        return f"Opened {url}."
    return f"Searched for {query or url}."
