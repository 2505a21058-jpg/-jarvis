"""skills/templates/search_wait_select_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchWaitSelectSelectSkill(StepRunnerSkill):
    name = "search_wait_select_select"
    description = "Searches, waits, and selects twice"
    STEPS = ['search', 'wait', 'select', 'select']
