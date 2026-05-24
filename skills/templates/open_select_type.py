"""skills/templates/open_select_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectTypeSkill(StepRunnerSkill):
    name = "open_select_type"
    description = "Opens, selects a field, and types"
    STEPS = ['open', 'select', 'type']
