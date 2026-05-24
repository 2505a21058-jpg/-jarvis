"""skills/templates/search_select_wait_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchSelectWaitSelectSkill(StepRunnerSkill):
    name = "search_select_wait_select"
    description = "Searches, selects, waits, and selects"
    STEPS = ['search', 'select', 'wait', 'select']
