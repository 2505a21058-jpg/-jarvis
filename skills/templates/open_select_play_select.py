"""skills/templates/open_select_play_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectPlaySelectSkill(StepRunnerSkill):
    name = "open_select_play_select"
    description = "Opens, selects, plays, and selects"
    STEPS = ['open', 'select', 'play', 'select']
