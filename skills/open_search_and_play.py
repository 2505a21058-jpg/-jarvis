"""Compatibility wrapper for the legacy open-search-and-play skill name."""

from skills.templates.open_search_play import OpenSearchPlaySkill


class OpenSearchAndPlaySkill(OpenSearchPlaySkill):
    name = "open_search_and_play"
    description = "Opens an app, searches for content, and opens the first result"
    timeout_seconds = 60.0
