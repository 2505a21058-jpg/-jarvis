"""skills/templates/close_select_open.py"""
from skills.step_runner import StepRunnerSkill


class CloseSelectOpenSkill(StepRunnerSkill):
    name = "close_select_open"
    description = "Closes, selects, and opens"
    STEPS = ['close', 'select', 'open']
