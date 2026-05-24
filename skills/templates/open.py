"""skills/templates/open.py"""
from skills.step_runner import StepRunnerSkill


class OpenSkill(StepRunnerSkill):
    name = "open"
    description = "Opens an application or website"
    STEPS = ['open']
