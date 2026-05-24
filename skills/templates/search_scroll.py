"""skills/templates/search_scroll.py"""
from skills.step_runner import StepRunnerSkill


class SearchScrollSkill(StepRunnerSkill):
    name = "search_scroll"
    description = "Searches and scrolls results"
    STEPS = ['search', 'scroll']
