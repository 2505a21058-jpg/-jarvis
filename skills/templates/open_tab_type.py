"""skills/templates/open_tab_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenTabTypeSkill(StepRunnerSkill):
    name = "open_tab_type"
    description = "Opens, opens new tab, and types"
    STEPS = ['open', 'tab', 'type']
