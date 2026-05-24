"""skills/templates/scroll_select_select.py"""
from skills.step_runner import StepRunnerSkill


class ScrollSelectSelectSkill(StepRunnerSkill):
    name = "scroll_select_select"
    description = "Scrolls and selects twice"
    STEPS = ['scroll', 'select', 'select']
