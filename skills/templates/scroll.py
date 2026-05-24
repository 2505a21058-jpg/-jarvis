"""skills/templates/scroll.py"""
from skills.step_runner import StepRunnerSkill


class ScrollSkill(StepRunnerSkill):
    name = "scroll"
    description = "Scrolls the active page"
    STEPS = ['scroll']
