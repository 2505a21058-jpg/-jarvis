"""skills/templates/search_play.py"""
from skills.step_runner import StepRunnerSkill


class SearchPlaySkill(StepRunnerSkill):
    name = "search_play"
    description = "Searches and plays content"
    STEPS = ['search', 'play']
