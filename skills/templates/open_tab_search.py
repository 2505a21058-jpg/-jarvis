"""skills/templates/open_tab_search.py"""
from skills.step_runner import StepRunnerSkill


class OpenTabSearchSkill(StepRunnerSkill):
    name = "open_tab_search"
    description = "Opens, opens new tab, and searches"
    STEPS = ['open', 'tab', 'search']
