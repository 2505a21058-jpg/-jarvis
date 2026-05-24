"""skills/templates/search_select_type.py"""
from skills.step_runner import StepRunnerSkill


class SearchSelectTypeSkill(StepRunnerSkill):
    name = "search_select_type"
    description = "Searches, selects, and types"
    STEPS = ['search', 'select', 'type']
