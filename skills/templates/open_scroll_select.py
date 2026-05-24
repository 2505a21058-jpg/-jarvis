"""skills/templates/open_scroll_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenScrollSelectSkill(StepRunnerSkill):
    name = "open_scroll_select"
    description = "Opens, scrolls, and selects"
    STEPS = ['open', 'scroll', 'select']
