"""skills/templates/select_type.py"""
from skills.step_runner import StepRunnerSkill


class SelectTypeSkill(StepRunnerSkill):
    name = "select_type"
    description = "Selects a field and types into it"
    STEPS = ['select', 'type']
