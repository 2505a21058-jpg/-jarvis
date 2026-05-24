"""skills/templates/search_select_type_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchSelectTypeSelectSkill(StepRunnerSkill):
    name = "search_select_type_select"
    description = "Searches, selects, types, and selects"
    STEPS = ['search', 'select', 'type', 'select']
