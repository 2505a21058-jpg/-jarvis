"""skills/templates/select_type_select_type.py"""
from skills.step_runner import StepRunnerSkill


class SelectTypeSelectTypeSkill(StepRunnerSkill):
    name = "select_type_select_type"
    description = "Selects, types, selects, types"
    STEPS = ['select', 'type', 'select', 'type']
