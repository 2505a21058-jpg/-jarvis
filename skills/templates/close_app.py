"""skills/templates/close_app.py"""
from skills.step_runner import StepRunnerSkill


class CloseAppSkill(StepRunnerSkill):
    name = "close_app"
    description = "Closes the active window"
    STEPS = ['close']
