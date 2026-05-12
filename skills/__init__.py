from skills.base import SkillBase, SkillResult
from skills.registry import SkillRegistry


_BOOTSTRAPPED = False


class ListSkillsSkill(SkillBase):
    name = "list_skills"
    description = "Lists all available skills Jarvis can perform"

    def execute(self, params: dict, state) -> SkillResult:
        skills = SkillRegistry.instance().list_skills()
        text = "\n".join(f"• {skill['name']}: {skill['description']}" for skill in skills)
        return SkillResult(success=True, output=f"Available skills:\n{text}")


def bootstrap_skills():
    global _BOOTSTRAPPED

    from skills.browser import BrowseSkill
    from skills.compose_email import ComposeEmailSkill
    from skills.gui_automate import GUIAutomateSkill
    from skills.launch_claude_code import LaunchClaudeCodeSkill
    from skills.run_code import RunCodeSkill
    from skills.open_and_search import OpenAndBrowseSkill, OpenAndSearchSkill
    from skills.open_and_type import OpenAndTypeSkill
    from skills.open_app import OpenAppSkill
    from skills.read_report import ReadReportSkill
    from skills.respond import RespondSkill
    from skills.reminder import ReminderSkill
    from skills.send_email import SendEmailSkill
    from skills.system_monitor import SystemMonitorSkill
    from skills.system_search import SystemSearchSkill
    from skills.type_text import TypeTextSkill
    from skills.web_summary import WebSummarySkill

    registry = SkillRegistry.instance()
    if not _BOOTSTRAPPED:
        registry.register_builtin(OpenAppSkill())
        registry.register_builtin(TypeTextSkill())
        registry.register_builtin(BrowseSkill())
        registry.register_builtin(ListSkillsSkill())
        registry.register_builtin(SendEmailSkill())
        registry.register_builtin(ReadReportSkill())
        registry.register_builtin(LaunchClaudeCodeSkill())
        registry.register_builtin(SystemSearchSkill())
        registry.register_builtin(SystemMonitorSkill())
        registry.register_builtin(ReminderSkill())
        registry.register_builtin(RespondSkill())
        registry.register_builtin(OpenAndSearchSkill())
        registry.register_builtin(OpenAndBrowseSkill())
        registry.register_builtin(OpenAndTypeSkill())
        registry.register_builtin(ComposeEmailSkill())
        registry.register_builtin(WebSummarySkill())
        registry.register_builtin(GUIAutomateSkill())
        registry.register_builtin(RunCodeSkill())
        _BOOTSTRAPPED = True
    return registry
