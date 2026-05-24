"""skills/templates/open_play.py"""
from skills.step_runner import StepRunnerSkill


class OpenPlaySkill(StepRunnerSkill):
    name = "open_play"
    description = "Opens an app and plays media"
    STEPS = ['open', 'play']
