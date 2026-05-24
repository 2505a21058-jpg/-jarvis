"""skills/templates/wait_select.py"""
from skills.step_runner import StepRunnerSkill


class WaitSelectSkill(StepRunnerSkill):
    name = "wait_select"
    description = "Waits then selects an element"
    STEPS = ['wait', 'select']
