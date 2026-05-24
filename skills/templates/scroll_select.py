"""skills/templates/scroll_select.py"""
from skills.step_runner import StepRunnerSkill


class ScrollSelectSkill(StepRunnerSkill):
    name = "scroll_select"
    description = "Scrolls then selects an item"
    STEPS = ['scroll', 'select']
