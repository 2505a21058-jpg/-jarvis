"""skills/templates/open_search_select_select_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectSelectTypeSkill(StepRunnerSkill):
    name = "open_search_select_select_type"
    description = "Opens, searches, selects twice, and types"
    STEPS = ['open', 'search', 'select', 'select', 'type']
