"""skills/templates/close_open.py"""
from skills.step_runner import StepRunnerSkill


class CloseOpenSkill(StepRunnerSkill):
    name = "close_open"
    description = "Closes a window then opens something"
    STEPS = ['close', 'open']
