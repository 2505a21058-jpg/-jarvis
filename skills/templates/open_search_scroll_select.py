"""skills/templates/open_search_scroll_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchScrollSelectSkill(StepRunnerSkill):
    name = "open_search_scroll_select"
    description = "Opens, searches, scrolls, and selects"
    STEPS = ['open', 'search', 'scroll', 'select']
