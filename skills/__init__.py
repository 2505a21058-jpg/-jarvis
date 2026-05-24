from skills.base import SkillBase, SkillResult
from skills.registry import SkillRegistry


_BOOTSTRAPPED = False


class ListSkillsSkill(SkillBase):
    name = "list_skills"
    description = "Lists all available skills Jarvis can perform"

    def execute(self, params: dict, state) -> SkillResult:
        skills = SkillRegistry.instance().list_skills_verbose()
        built_in = [skill for skill in skills if skill["source"] == "builtin"]
        learned = [skill for skill in skills if skill["source"] == "learned"]

        lines = ["Built-in skills:"]
        for skill in built_in:
            lines.append(f"  - {skill['name']} (v{skill['version']})")

        if learned:
            lines.append("")
            lines.append("Learned skills:")
            for skill in learned:
                conflict_note = " ! conflicts with built-in" if skill["conflict"] else ""
                lines.append(f"  - {skill['name']} (v{skill['version']}){conflict_note}")

        return SkillResult(success=True, output="\n".join(lines))


def get_registry():
    return bootstrap_skills()


def bootstrap_skills():
    global _BOOTSTRAPPED

    from skills.browser import BrowseSkill
    from skills.compose_email import ComposeEmailSkill
    from skills.computer_control import ComputerControlSkill
    from skills.gui_automate import GUIAutomateSkill
    from skills.launch_claude_code import LaunchClaudeCodeSkill
    from skills.type_text import TypeTextSkill
    from skills.run_code import RunCodeSkill
    from skills.open_and_search import OpenAndBrowseSkill, OpenAndSearchSkill
    from skills.open_and_type import OpenAndTypeSkill
    from skills.open_search_and_play import OpenSearchAndPlaySkill
    from skills.open_app import OpenAppSkill
    from skills.read_report import ReadReportSkill
    from skills.respond import RespondSkill
    from skills.reminder import ReminderSkill
    from skills.send_email import SendEmailSkill
    from skills.system_monitor import SystemMonitorSkill
    from skills.system_search import SystemSearchSkill
    from skills.train_skill import PNRSkill, LiveTrainSkill
    from skills.weather_skill import WeatherSkill
    from skills.codebase_explorer import CodebaseExplorerSkill
    from skills.web_research import (
        CodebaseExplorerAliasSkill,
        DeepResearchSkill,
        QuickSearchAliasSkill,
        QuickSearchSkill,
        WebResearchAliasSkill,
        WebResearchSkill,
    )
    from skills.read_url import ReadUrlSkill

    registry = SkillRegistry.instance()
    if not _BOOTSTRAPPED or not registry.list_skills():
        registry.register_builtin(OpenAppSkill())
        registry.register_builtin(BrowseSkill())
        registry.register_builtin(ListSkillsSkill())
        registry.register_builtin(SendEmailSkill())
        registry.register_builtin(ReadReportSkill())
        registry.register_builtin(LaunchClaudeCodeSkill())
        registry.register_builtin(SystemSearchSkill())
        registry.register_builtin(SystemMonitorSkill())
        registry.register_builtin(ReminderSkill())
        registry.register_builtin(RespondSkill())
        registry.register_builtin(TypeTextSkill())
        registry.register_builtin(OpenAndSearchSkill())
        registry.register_builtin(OpenAndBrowseSkill())
        registry.register_builtin(OpenAndTypeSkill())
        registry.register_builtin(OpenSearchAndPlaySkill())
        registry.register_builtin(ComposeEmailSkill())
        registry.register_builtin(ComputerControlSkill())
        registry.register_builtin(WebResearchSkill())
        registry.register_builtin(WebResearchAliasSkill())
        registry.register_builtin(QuickSearchSkill())
        registry.register_builtin(QuickSearchAliasSkill())
        registry.register_builtin(GUIAutomateSkill())
        registry.register_builtin(RunCodeSkill())
        registry.register_builtin(PNRSkill())
        registry.register_builtin(LiveTrainSkill())
        registry.register_builtin(WeatherSkill())
        registry.register_builtin(DeepResearchSkill())
        registry.register_builtin(CodebaseExplorerSkill())
        registry.register_builtin(CodebaseExplorerAliasSkill())
        registry.register_builtin(ReadUrlSkill())
        _register_all_templates(registry)
        _init_skill_catalog(registry)
        _BOOTSTRAPPED = True
    return registry


def _init_skill_catalog(registry):
    """Initialize the skill catalog and wire it into the registry."""
    from skills.catalog import _init_default_catalog
    catalog = _init_default_catalog(registry)
    import logging
    logging.getLogger("jarvis.skills").info(
        "Skill catalog initialized with %d manifests", len(catalog._manifests)
    )


def _register_all_templates(registry):
    """Register all 113 template skills from skills/templates/."""
    from skills.templates import (
        CloseAppSkill, CloseOpenSkill, CloseSelectSkill, CloseSelectOpenSkill,
        CloseSelectOpenSelectSkill, OpenSkill, OpenCloseSkill, OpenPlaySkill,
        OpenPlayTypeSkill, OpenScrollSkill, OpenScrollSelectSkill,
        OpenScrollSelectSelectSkill, OpenScrollTypeSkill, OpenSearchSkill,
        OpenSearchPlaySkill, OpenSearchPlayTypeSkill, OpenSearchScrollSkill,
        OpenSearchScrollSelectSkill, OpenSearchScrollSelectSelectSkill,
        OpenSearchScrollSelectTypeSkill, OpenSearchScrollTypeSkill,
        OpenSearchScrollTypeSelectSkill, OpenSearchSearchSelectSkill,
        OpenSearchSearchSelectSelectSkill, OpenSearchSelectSkill,
        OpenSearchSelectPlaySkill, OpenSearchSelectPlaySelectSkill,
        OpenSearchSelectScrollSkill, OpenSearchSelectSelectSkill,
        OpenSearchSelectSelectPlaySkill, OpenSearchSelectSelectScrollSkill,
        OpenSearchSelectSelectSelectSkill, OpenSearchSelectSelectTypeSkill,
        OpenSearchSelectShortcutSkill, OpenSearchSelectTypeSkill,
        OpenSearchSelectTypeSelectSkill, OpenSearchTypeSkill,
        OpenSearchWaitSelectSkill, OpenSearchWaitSelectSelectSkill,
        OpenSelectSkill, OpenSelectPlaySkill, OpenSelectPlaySelectSkill,
        OpenSelectSelectTypeSelectSkill, OpenSelectShortcutSkill,
        OpenSelectTypeSkill, OpenSelectTypeSelectSkill,
        OpenSelectTypeSelectSelectSkill, OpenSelectTypeShortcutSkill,
        OpenSelectTypeTypeSkill, OpenTabSearchSkill,
        OpenTabSearchPlaySelectSkill, OpenTabSearchSelectSkill,
        OpenTabSearchSelectSelectSkill, OpenTabSearchTypeSkill,
        OpenTabTypeSkill, OpenTypeSkill, OpenTypeSelectSkill,
        OpenTypeSelectShortcutSkill, OpenTypeShortcutSkill,
        OpenWaitSearchSelectSkill, OpenWaitSearchSelectSelectSkill,
        OpenWaitSelectSkill, OpenWaitTypeSkill, PlaySkill, PlaySelectSkill,
        ScrollSkill, ScrollSelectSkill, ScrollSelectSelectSkill,
        ScrollSelectSelectSelectSkill, ScrollSelectSelectSelectSelectSkill,
        SearchSkill, SearchPlaySkill, SearchScrollSkill,
        SearchScrollSelectSkill, SearchScrollSelectSelectSkill,
        SearchScrollSelectSelectSelectSkill,
        SearchScrollSelectTypeSelectSkill, SearchScrollTypeSkill,
        SearchScrollTypeSelectSkill, SearchSelectSkill, SearchSelectPlaySkill,
        SearchSelectSelectTypeSelectSkill, SearchSelectTypeSkill,
        SearchSelectTypeSelectSkill, SearchSelectWaitSelectSkill,
        SearchSelectWaitSelectSelectSkill, SearchTypeSkill,
        SearchWaitScrollSkill, SearchWaitSelectSkill,
        SearchWaitSelectSelectSkill, SearchWaitSelectSelectSelectSkill,
        SelectSkill, SelectPlaySkill, SelectPlaySelectSkill, SelectScrollSkill,
        SelectSelectPlaySkill, SelectSelectPlayScrollSkill,
        SelectSelectTypeSkill, SelectShortcutSkill, SelectTypeSkill,
        SelectTypeSelectSkill, SelectTypeSelectTypeSkill,
        SelectTypeShortcutWaitSelectSkill, SelectTypeTypeSkill, ShortcutSkill,
        TypeSkill, TypeSelectSkill, TypeSelectShortcutSkill, TypeShortcutSkill,
        TypeTypeTypeSkill, WaitScrollSelectSkill, WaitSelectSkill, WaitTypeSkill,
    )
    for cls in (
        CloseAppSkill, CloseOpenSkill, CloseSelectSkill, CloseSelectOpenSkill,
        CloseSelectOpenSelectSkill, OpenSkill, OpenCloseSkill, OpenPlaySkill,
        OpenPlayTypeSkill, OpenScrollSkill, OpenScrollSelectSkill,
        OpenScrollSelectSelectSkill, OpenScrollTypeSkill, OpenSearchSkill,
        OpenSearchPlaySkill, OpenSearchPlayTypeSkill, OpenSearchScrollSkill,
        OpenSearchScrollSelectSkill, OpenSearchScrollSelectSelectSkill,
        OpenSearchScrollSelectTypeSkill, OpenSearchScrollTypeSkill,
        OpenSearchScrollTypeSelectSkill, OpenSearchSearchSelectSkill,
        OpenSearchSearchSelectSelectSkill, OpenSearchSelectSkill,
        OpenSearchSelectPlaySkill, OpenSearchSelectPlaySelectSkill,
        OpenSearchSelectScrollSkill, OpenSearchSelectSelectSkill,
        OpenSearchSelectSelectPlaySkill, OpenSearchSelectSelectScrollSkill,
        OpenSearchSelectSelectSelectSkill, OpenSearchSelectSelectTypeSkill,
        OpenSearchSelectShortcutSkill, OpenSearchSelectTypeSkill,
        OpenSearchSelectTypeSelectSkill, OpenSearchTypeSkill,
        OpenSearchWaitSelectSkill, OpenSearchWaitSelectSelectSkill,
        OpenSelectSkill, OpenSelectPlaySkill, OpenSelectPlaySelectSkill,
        OpenSelectSelectTypeSelectSkill, OpenSelectShortcutSkill,
        OpenSelectTypeSkill, OpenSelectTypeSelectSkill,
        OpenSelectTypeSelectSelectSkill, OpenSelectTypeShortcutSkill,
        OpenSelectTypeTypeSkill, OpenTabSearchSkill,
        OpenTabSearchPlaySelectSkill, OpenTabSearchSelectSkill,
        OpenTabSearchSelectSelectSkill, OpenTabSearchTypeSkill,
        OpenTabTypeSkill, OpenTypeSkill, OpenTypeSelectSkill,
        OpenTypeSelectShortcutSkill, OpenTypeShortcutSkill,
        OpenWaitSearchSelectSkill, OpenWaitSearchSelectSelectSkill,
        OpenWaitSelectSkill, OpenWaitTypeSkill, PlaySkill, PlaySelectSkill,
        ScrollSkill, ScrollSelectSkill, ScrollSelectSelectSkill,
        ScrollSelectSelectSelectSkill, ScrollSelectSelectSelectSelectSkill,
        SearchSkill, SearchPlaySkill, SearchScrollSkill,
        SearchScrollSelectSkill, SearchScrollSelectSelectSkill,
        SearchScrollSelectSelectSelectSkill,
        SearchScrollSelectTypeSelectSkill, SearchScrollTypeSkill,
        SearchScrollTypeSelectSkill, SearchSelectSkill, SearchSelectPlaySkill,
        SearchSelectSelectTypeSelectSkill, SearchSelectTypeSkill,
        SearchSelectTypeSelectSkill, SearchSelectWaitSelectSkill,
        SearchSelectWaitSelectSelectSkill, SearchTypeSkill,
        SearchWaitScrollSkill, SearchWaitSelectSkill,
        SearchWaitSelectSelectSkill, SearchWaitSelectSelectSelectSkill,
        SelectSkill, SelectPlaySkill, SelectPlaySelectSkill, SelectScrollSkill,
        SelectSelectPlaySkill, SelectSelectPlayScrollSkill,
        SelectSelectTypeSkill, SelectShortcutSkill, SelectTypeSkill,
        SelectTypeSelectSkill, SelectTypeSelectTypeSkill,
        SelectTypeShortcutWaitSelectSkill, SelectTypeTypeSkill, ShortcutSkill,
        TypeSkill, TypeSelectSkill, TypeSelectShortcutSkill, TypeShortcutSkill,
        TypeTypeTypeSkill, WaitScrollSelectSkill, WaitSelectSkill, WaitTypeSkill,
    ):
        try:
            registry.register_builtin(cls())
        except Exception:
            pass
