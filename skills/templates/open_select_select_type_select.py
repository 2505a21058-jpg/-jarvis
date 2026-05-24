"""skills/templates/open_select_select_type_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectSelectTypeSelectSkill(StepRunnerSkill):
    name = "open_select_select_type_select"
    description = "Opens, selects twice, types, and selects"
    STEPS = ['open', 'select', 'select', 'type', 'select']
