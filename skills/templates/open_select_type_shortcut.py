"""skills/templates/open_select_type_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectTypeShortcutSkill(StepRunnerSkill):
    name = "open_select_type_shortcut"
    description = "Opens, selects, types, and executes shortcut"
    STEPS = ['open', 'select', 'type', 'shortcut']
