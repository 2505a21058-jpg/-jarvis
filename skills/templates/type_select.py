"""skills/templates/type_select.py"""
from skills.step_runner import StepRunnerSkill


class TypeSelectSkill(StepRunnerSkill):
    name = "type_select"
    description = "Types text then selects a result"
    STEPS = ['type', 'select']
