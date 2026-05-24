"""skills/templates/play_select.py"""
from skills.step_runner import StepRunnerSkill


class PlaySelectSkill(StepRunnerSkill):
    name = "play_select"
    description = "Plays content then selects something"
    STEPS = ['play', 'select']
