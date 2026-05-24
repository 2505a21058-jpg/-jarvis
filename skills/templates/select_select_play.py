"""skills/templates/select_select_play.py"""
from skills.step_runner import StepRunnerSkill


class SelectSelectPlaySkill(StepRunnerSkill):
    name = "select_select_play"
    description = "Selects twice then plays"
    STEPS = ['select', 'select', 'play']
