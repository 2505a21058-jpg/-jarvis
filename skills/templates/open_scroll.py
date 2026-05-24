"""skills/templates/open_scroll.py"""
from skills.step_runner import StepRunnerSkill


class OpenScrollSkill(StepRunnerSkill):
    name = "open_scroll"
    description = "Opens an app and scrolls"
    STEPS = ['open', 'scroll']
