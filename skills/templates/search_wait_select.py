"""skills/templates/search_wait_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchWaitSelectSkill(StepRunnerSkill):
    name = "search_wait_select"
    description = "Searches, waits, and selects"
    STEPS = ['search', 'wait', 'select']
