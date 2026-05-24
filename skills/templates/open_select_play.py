"""skills/templates/open_select_play.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectPlaySkill(StepRunnerSkill):
    name = "open_select_play"
    description = "Opens, selects, and plays"
    STEPS = ['open', 'select', 'play']
