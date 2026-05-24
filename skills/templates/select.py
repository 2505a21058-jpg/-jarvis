"""skills/templates/select.py"""
from skills.step_runner import StepRunnerSkill


class SelectSkill(StepRunnerSkill):
    name = "select"
    description = "Selects or clicks a target element"
    STEPS = ['select']
