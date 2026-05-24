"""skills/templates/select_select_type.py"""
from skills.step_runner import StepRunnerSkill


class SelectSelectTypeSkill(StepRunnerSkill):
    name = "select_select_type"
    description = "Selects, selects again, and types"
    STEPS = ['select', 'select', 'type']
