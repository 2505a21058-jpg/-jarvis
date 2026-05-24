"""skills/templates/open_wait_search_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenWaitSearchSelectSkill(StepRunnerSkill):
    name = "open_wait_search_select"
    description = "Opens, waits, searches, and selects"
    STEPS = ['open', 'wait', 'search', 'select']
