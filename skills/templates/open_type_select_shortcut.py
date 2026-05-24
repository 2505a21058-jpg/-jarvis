"""skills/templates/open_type_select_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class OpenTypeSelectShortcutSkill(StepRunnerSkill):
    name = "open_type_select_shortcut"
    description = "Opens, types, selects, and executes shortcut"
    STEPS = ['open', 'type', 'select', 'shortcut']
