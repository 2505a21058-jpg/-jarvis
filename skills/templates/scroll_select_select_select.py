"""skills/templates/scroll_select_select_select.py"""
from skills.step_runner import StepRunnerSkill


class ScrollSelectSelectSelectSkill(StepRunnerSkill):
    name = "scroll_select_select_select"
    description = "Scrolls and selects three times"
    STEPS = ['scroll', 'select', 'select', 'select']
