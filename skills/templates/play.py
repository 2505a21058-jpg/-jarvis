"""skills/templates/play.py"""
from skills.step_runner import StepRunnerSkill


class PlaySkill(StepRunnerSkill):
    name = "play"
    description = "Presses the play button"
    STEPS = ['play']
