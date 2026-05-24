"""skills/templates/open_play_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenPlayTypeSkill(StepRunnerSkill):
    name = "open_play_type"
    description = "Opens, plays, and types"
    STEPS = ['open', 'play', 'type']
