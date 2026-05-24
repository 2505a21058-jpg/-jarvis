"""skills/templates/open_tab_search_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenTabSearchSelectSelectSkill(StepRunnerSkill):
    name = "open_tab_search_select_select"
    description = "Opens, opens tab, searches, and selects twice"
    STEPS = ['open', 'tab', 'search', 'select', 'select']
