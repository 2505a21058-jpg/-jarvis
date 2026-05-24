"""skills/templates/open_search_wait_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchWaitSelectSkill(StepRunnerSkill):
    name = "open_search_wait_select"
    description = "Opens, searches, waits, and selects"
    STEPS = ['open', 'search', 'wait', 'select']
