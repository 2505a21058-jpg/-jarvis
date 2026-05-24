"""skills/templates/search_wait_scroll.py"""
from skills.step_runner import StepRunnerSkill


class SearchWaitScrollSkill(StepRunnerSkill):
    name = "search_wait_scroll"
    description = "Searches, waits, and scrolls"
    STEPS = ['search', 'wait', 'scroll']
