"""skills/templates/search_type.py"""
from skills.step_runner import StepRunnerSkill


class SearchTypeSkill(StepRunnerSkill):
    name = "search_type"
    description = "Searches then types into a field"
    STEPS = ['search', 'type']
