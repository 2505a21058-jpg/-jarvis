"""skills/templates/open_select_type_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectTypeTypeSkill(StepRunnerSkill):
    name = "open_select_type_type"
    description = "Opens, selects, and types twice"
    STEPS = ['open', 'select', 'type', 'type']
