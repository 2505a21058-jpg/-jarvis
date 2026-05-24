"""skills/templates/open_tab_search_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenTabSearchSelectSkill(StepRunnerSkill):
    name = "open_tab_search_select"
    description = "Opens, opens tab, searches, and selects"
    STEPS = ['open', 'tab', 'search', 'select']
