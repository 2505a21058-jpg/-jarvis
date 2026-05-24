"""skills/templates/close_select.py"""
from skills.step_runner import StepRunnerSkill


class CloseSelectSkill(StepRunnerSkill):
    name = "close_select"
    description = "Closes a window then selects something"
    STEPS = ['close', 'select']
