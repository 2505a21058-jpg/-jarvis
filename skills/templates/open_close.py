"""skills/templates/open_close.py"""
from skills.step_runner import StepRunnerSkill


class OpenCloseSkill(StepRunnerSkill):
    name = "open_close"
    description = "Opens and closes an app"
    STEPS = ['open', 'close']
