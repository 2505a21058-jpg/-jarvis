"""skills/templates/open_type_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenTypeSelectSkill(StepRunnerSkill):
    name = "open_type_select"
    description = "Opens, types, and selects result"
    STEPS = ['open', 'type', 'select']
