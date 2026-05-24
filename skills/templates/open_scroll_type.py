"""skills/templates/open_scroll_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenScrollTypeSkill(StepRunnerSkill):
    name = "open_scroll_type"
    description = "Opens, scrolls, and types"
    STEPS = ['open', 'scroll', 'type']
