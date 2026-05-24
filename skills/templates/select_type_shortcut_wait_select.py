"""skills/templates/select_type_shortcut_wait_select.py"""
from skills.step_runner import StepRunnerSkill


class SelectTypeShortcutWaitSelectSkill(StepRunnerSkill):
    name = "select_type_shortcut_wait_select"
    description = "Selects, types, shortcut, waits, and selects"
    STEPS = ['select', 'type', 'shortcut', 'wait', 'select']
