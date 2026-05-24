"""skills/templates/type_select_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class TypeSelectShortcutSkill(StepRunnerSkill):
    name = "type_select_shortcut"
    description = "Types, selects, and executes shortcut"
    STEPS = ['type', 'select', 'shortcut']
