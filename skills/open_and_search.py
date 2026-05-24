"""Compatibility wrappers for legacy open-and-search skill names."""

from __future__ import annotations

from skills.browser import BrowseSkill
from skills.templates.open_search import OpenSearchSkill


class OpenAndSearchSkill(OpenSearchSkill):
    name = "open_and_search"
    description = "Opens an app or website and searches for something within it"
    timeout_seconds = 45.0


class OpenAndBrowseSkill(BrowseSkill):
    name = "open_and_browse"
    description = "Opens an app and navigates to a specific URL"
    timeout_seconds = 30.0
