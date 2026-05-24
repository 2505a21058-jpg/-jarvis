"""skills/templates/search_scroll_select_select_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchScrollSelectSelectSelectSkill(StepRunnerSkill):
    name = "search_scroll_select_select_select"
    description = "Searches, scrolls, and selects three times"
    STEPS = ['search', 'scroll', 'select', 'select', 'select']
