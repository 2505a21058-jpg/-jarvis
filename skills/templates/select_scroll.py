"""skills/templates/select_scroll.py"""
from skills.step_runner import StepRunnerSkill


class SelectScrollSkill(StepRunnerSkill):
    name = "select_scroll"
    description = "Selects an item and scrolls"
    STEPS = ['select', 'scroll']
