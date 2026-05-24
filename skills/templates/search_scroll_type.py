"""skills/templates/search_scroll_type.py"""
from skills.step_runner import StepRunnerSkill


class SearchScrollTypeSkill(StepRunnerSkill):
    name = "search_scroll_type"
    description = "Searches, scrolls, and types"
    STEPS = ['search', 'scroll', 'type']
