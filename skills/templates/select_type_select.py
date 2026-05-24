"""skills/templates/select_type_select.py"""
from skills.step_runner import StepRunnerSkill


class SelectTypeSelectSkill(StepRunnerSkill):
    name = "select_type_select"
    description = "Selects, types, and selects"
    STEPS = ['select', 'type', 'select']
