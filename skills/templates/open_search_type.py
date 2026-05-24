"""skills/templates/open_search_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchTypeSkill(StepRunnerSkill):
    name = "open_search_type"
    description = "Opens, searches, and types"
    STEPS = ['open', 'search', 'type']
