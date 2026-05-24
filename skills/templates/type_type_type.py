"""skills/templates/type_type_type.py"""
from skills.step_runner import StepRunnerSkill


class TypeTypeTypeSkill(StepRunnerSkill):
    name = "type_type_type"
    description = "Types text three times"
    STEPS = ['type', 'type', 'type']
