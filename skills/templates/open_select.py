"""skills/templates/open_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectSkill(StepRunnerSkill):
    name = "open_select"
    description = "Opens an app and selects a target"
    STEPS = ['open', 'select']
