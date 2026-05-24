"""skills/templates/open_type_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class OpenTypeShortcutSkill(StepRunnerSkill):
    name = "open_type_shortcut"
    description = "Opens, types, and executes shortcut"
    STEPS = ['open', 'type', 'shortcut']
