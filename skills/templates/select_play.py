"""skills/templates/select_play.py"""
from skills.step_runner import StepRunnerSkill


class SelectPlaySkill(StepRunnerSkill):
    name = "select_play"
    description = "Selects an item and plays it"
    STEPS = ['select', 'play']
