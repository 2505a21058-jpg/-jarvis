"""skills/templates/open_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenTypeSkill(StepRunnerSkill):
    name = "open_type"
    description = "Opens an app and types text"
    STEPS = ['open', 'type']
