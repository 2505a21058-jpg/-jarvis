"""skills/templates/open_scroll_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenScrollSelectSelectSkill(StepRunnerSkill):
    name = "open_scroll_select_select"
    description = "Opens, scrolls, and selects twice"
    STEPS = ['open', 'scroll', 'select', 'select']
