"""skills/templates/search_select_select_type_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchSelectSelectTypeSelectSkill(StepRunnerSkill):
    name = "search_select_select_type_select"
    description = "Searches, selects twice, types, and selects"
    STEPS = ['search', 'select', 'select', 'type', 'select']
