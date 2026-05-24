"""skills/templates/open_wait_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenWaitTypeSkill(StepRunnerSkill):
    name = "open_wait_type"
    description = "Opens, waits, and types"
    STEPS = ['open', 'wait', 'type']
