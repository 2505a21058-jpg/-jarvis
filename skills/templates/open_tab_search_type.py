"""skills/templates/open_tab_search_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenTabSearchTypeSkill(StepRunnerSkill):
    name = "open_tab_search_type"
    description = "Opens, opens tab, searches, and types"
    STEPS = ['open', 'tab', 'search', 'type']
