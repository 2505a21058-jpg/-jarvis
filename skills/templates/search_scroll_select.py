"""skills/templates/search_scroll_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchScrollSelectSkill(StepRunnerSkill):
    name = "search_scroll_select"
    description = "Searches, scrolls, and selects"
    STEPS = ['search', 'scroll', 'select']
