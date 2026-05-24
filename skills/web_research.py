"""
skills/web_research.py

Skill wrappers for the local internet access layer.
Registered as: web_summary, web_search, and web_research.
"""

from __future__ import annotations

from skills import SkillBase, SkillResult


class WebResearchSkill(SkillBase):
    name = "web_summary"
    description = "Research a topic using live web search and return a synthesized answer"
    timeout_seconds = 40.0

    def execute(self, params: dict, state) -> SkillResult:
        from internet.web_agent import research

        search_query = str(params.get("topic") or params.get("query") or "").strip()
        depth = str(params.get("depth") or "normal").strip() or "normal"
        if not search_query:
            return SkillResult(success=False, output=None, error="Please specify a topic to research.", skill_name=self.name)
        return SkillResult(success=True, output=research(search_query, depth=depth), skill_name=self.name)


class WebResearchAliasSkill(WebResearchSkill):
    name = "web_research"
    description = "Research a topic using live web search and return a synthesized answer"


class QuickSearchSkill(SkillBase):
    name = "web_search"
    description = "Quick web search returning synthesized snippets"
    timeout_seconds = 10.0

    def execute(self, params: dict, state) -> SkillResult:
        from internet.web_agent import quick_answer

        query = str(params.get("query") or params.get("topic") or "").strip()
        if not query:
            return SkillResult(success=False, output=None, error="Please specify a search query.", skill_name=self.name)
        return SkillResult(success=True, output=quick_answer(query), skill_name=self.name)


class QuickSearchAliasSkill(QuickSearchSkill):
    name = "quick_search"
    description = "Quick web search returning synthesized snippets"


class DeepResearchSkill(SkillBase):
    name = "deep_research"
    description = "Deep multi-query research — generates sub-questions, searches each in parallel, and synthesizes a comprehensive comparison"
    timeout_seconds = 120.0

    def execute(self, params: dict, state) -> SkillResult:
        from internet.deep_research import deep_research

        topic = str(params.get("topic") or params.get("query") or "").strip()
        depth = int(params.get("depth", 4))
        output_format = str(params.get("format", "auto")).strip().lower()
        if not topic:
            return SkillResult(success=False, output=None, error="Please specify a research topic.", skill_name=self.name)
        result = deep_research(topic, depth=depth, format=output_format)
        return SkillResult(success=True, output=result, skill_name=self.name)


class CodebaseExplorerAliasSkill(SkillBase):
    name = "codebase_explorer"
    description = "Explore the Jarvis codebase to answer questions about how it works"
    timeout_seconds = 30.0

    def execute(self, params: dict, state) -> SkillResult:
        from skills.codebase_explorer import CodebaseExplorerSkill

        inner = CodebaseExplorerSkill()
        return inner.execute(params, state)
