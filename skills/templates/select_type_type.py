"""skills/templates/select_type_type.py"""
from skills.step_runner import StepRunnerSkill


class SelectTypeTypeSkill(StepRunnerSkill):
    name = "select_type_type"
    description = "Selects then types twice"
    STEPS = ['select', 'type', 'type']
