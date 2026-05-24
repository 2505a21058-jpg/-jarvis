"""skills/templates/search_scroll_type_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchScrollTypeSelectSkill(StepRunnerSkill):
    name = "search_scroll_type_select"
    description = "Searches, scrolls, types, and selects"
    STEPS = ['search', 'scroll', 'type', 'select']
