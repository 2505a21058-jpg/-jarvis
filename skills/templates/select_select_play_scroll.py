"""skills/templates/select_select_play_scroll.py"""
from skills.step_runner import StepRunnerSkill


class SelectSelectPlayScrollSkill(StepRunnerSkill):
    name = "select_select_play_scroll"
    description = "Selects twice, plays, and scrolls"
    STEPS = ['select', 'select', 'play', 'scroll']
