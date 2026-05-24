"""skills/templates/open_search_scroll_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchScrollTypeSkill(StepRunnerSkill):
    name = "open_search_scroll_type"
    description = "Opens, searches, scrolls, and types"
    STEPS = ['open', 'search', 'scroll', 'type']
