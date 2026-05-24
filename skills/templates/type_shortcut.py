"""skills/templates/type_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class TypeShortcutSkill(StepRunnerSkill):
    name = "type_shortcut"
    description = "Types text then executes a shortcut"
    STEPS = ['type', 'shortcut']
