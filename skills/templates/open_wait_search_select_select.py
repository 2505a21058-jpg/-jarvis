"""skills/templates/open_wait_search_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenWaitSearchSelectSelectSkill(StepRunnerSkill):
    name = "open_wait_search_select_select"
    description = "Opens, waits, searches, and selects twice"
    STEPS = ['open', 'wait', 'search', 'select', 'select']
