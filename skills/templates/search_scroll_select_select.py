"""skills/templates/search_scroll_select_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchScrollSelectSelectSkill(StepRunnerSkill):
    name = "search_scroll_select_select"
    description = "Searches, scrolls, and selects twice"
    STEPS = ['search', 'scroll', 'select', 'select']
