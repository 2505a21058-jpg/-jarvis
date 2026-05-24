"""skills/templates/open_search_select_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectTypeSkill(StepRunnerSkill):
    name = "open_search_select_type"
    description = "Opens, searches, selects, and types"
    STEPS = ['open', 'search', 'select', 'type']
