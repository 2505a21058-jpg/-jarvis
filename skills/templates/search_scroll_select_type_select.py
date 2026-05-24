"""skills/templates/search_scroll_select_type_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchScrollSelectTypeSelectSkill(StepRunnerSkill):
    name = "search_scroll_select_type_select"
    description = "Searches, scrolls, selects, types, and selects"
    STEPS = ['search', 'scroll', 'select', 'type', 'select']
