"""skills/templates/open_search_wait_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchWaitSelectSelectSkill(StepRunnerSkill):
    name = "open_search_wait_select_select"
    description = "Opens, searches, waits, and selects twice"
    STEPS = ['open', 'search', 'wait', 'select', 'select']
