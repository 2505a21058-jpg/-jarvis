"""skills/templates/type.py"""
from skills.step_runner import StepRunnerSkill


class TypeSkill(StepRunnerSkill):
    name = "type"
    description = "Types text into a focused element"
    STEPS = ['type']
