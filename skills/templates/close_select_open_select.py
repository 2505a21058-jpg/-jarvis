"""skills/templates/close_select_open_select.py"""
from skills.step_runner import StepRunnerSkill


class CloseSelectOpenSelectSkill(StepRunnerSkill):
    name = "close_select_open_select"
    description = "Closes, selects, opens, and selects"
    STEPS = ['close', 'select', 'open', 'select']
