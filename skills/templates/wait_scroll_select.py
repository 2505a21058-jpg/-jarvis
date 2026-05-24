"""skills/templates/wait_scroll_select.py"""
from skills.step_runner import StepRunnerSkill


class WaitScrollSelectSkill(StepRunnerSkill):
    name = "wait_scroll_select"
    description = "Waits, scrolls, and selects"
    STEPS = ['wait', 'scroll', 'select']
