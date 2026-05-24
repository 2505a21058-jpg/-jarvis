"""skills/templates/wait_type.py"""
from skills.step_runner import StepRunnerSkill


class WaitTypeSkill(StepRunnerSkill):
    name = "wait_type"
    description = "Waits then types into a field"
    STEPS = ['wait', 'type']
