"""skills/templates/open_wait_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenWaitSelectSkill(StepRunnerSkill):
    name = "open_wait_select"
    description = "Opens, waits, and selects"
    STEPS = ['open', 'wait', 'select']
