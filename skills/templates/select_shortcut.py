"""skills/templates/select_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class SelectShortcutSkill(StepRunnerSkill):
    name = "select_shortcut"
    description = "Selects an item and triggers a shortcut"
    STEPS = ['select', 'shortcut']
