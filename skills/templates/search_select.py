"""skills/templates/search_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchSelectSkill(StepRunnerSkill):
    name = "search_select"
    description = "Searches and selects a result"
    STEPS = ['search', 'select']
