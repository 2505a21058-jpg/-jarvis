"""skills/templates/scroll_select_select_select_select.py"""
from skills.step_runner import StepRunnerSkill


class ScrollSelectSelectSelectSelectSkill(StepRunnerSkill):
    name = "scroll_select_select_select_select"
    description = "Scrolls and selects four times"
    STEPS = ['scroll', 'select', 'select', 'select', 'select']
