"""skills/templates/search_select_wait_select_select.py"""
from skills.step_runner import StepRunnerSkill


class SearchSelectWaitSelectSelectSkill(StepRunnerSkill):
    name = "search_select_wait_select_select"
    description = "Searches, selects, waits, and selects twice"
    STEPS = ['search', 'select', 'wait', 'select', 'select']
