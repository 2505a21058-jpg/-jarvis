"""skills/templates/shortcut.py"""
from skills.step_runner import StepRunnerSkill


class ShortcutSkill(StepRunnerSkill):
    name = "shortcut"
    description = "Executes a keyboard shortcut"
    STEPS = ['shortcut']
