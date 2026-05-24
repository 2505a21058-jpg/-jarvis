"""skills/templates/select_play_select.py"""
from skills.step_runner import StepRunnerSkill


class SelectPlaySelectSkill(StepRunnerSkill):
    name = "select_play_select"
    description = "Selects, plays, and selects"
    STEPS = ['select', 'play', 'select']
