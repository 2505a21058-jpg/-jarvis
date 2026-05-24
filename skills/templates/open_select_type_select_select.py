"""skills/templates/open_select_type_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSelectTypeSelectSelectSkill(StepRunnerSkill):
    name = "open_select_type_select_select"
    description = "Opens, selects, types, and selects twice"
    STEPS = ['open', 'select', 'type', 'select', 'select']
