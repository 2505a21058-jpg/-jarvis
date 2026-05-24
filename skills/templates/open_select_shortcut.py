"""skills/templates/open_select_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectShortcutSkill(StepRunnerSkill):
    name = "open_select_shortcut"
    description = "Opens, selects, and executes shortcut"
    STEPS = ['open', 'select', 'shortcut']
