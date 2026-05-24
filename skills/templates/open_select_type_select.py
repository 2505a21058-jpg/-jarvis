"""skills/templates/open_select_type_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectTypeSelectSkill(StepRunnerSkill):
    name = "open_select_type_select"
    description = "Opens, selects, types, and selects"
    STEPS = ['open', 'select', 'type', 'select']
