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
    from skills.launch_claude_code import LaunchClaudeCodeSkill
    from skills.open_app import OpenAppSkill
    from skills.read_report import ReadReportSkill
    from skills.reminder import ReminderSkill
    from skills.send_email import SendEmailSkill
    from skills.system_monitor import SystemMonitorSkill
    from skills.system_search import SystemSearchSkill
    from skills.type_text import TypeTextSkill

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
        _BOOTSTRAPPED = True
    return registry
