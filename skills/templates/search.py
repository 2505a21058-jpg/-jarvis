"""skills/templates/search.py"""
from skills.step_runner import StepRunnerSkill


class SearchSkill(StepRunnerSkill):
    name = "search"
    description = "Searches for content in the active application"
    STEPS = ['search']
