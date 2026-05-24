"""skills/templates/search_wait_select_select_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchWaitSelectSelectSelectSkill(StepRunnerSkill):
    name = "search_wait_select_select_select"
    description = "Searches, waits, and selects three times"
    STEPS = ['search', 'wait', 'select', 'select', 'select']
