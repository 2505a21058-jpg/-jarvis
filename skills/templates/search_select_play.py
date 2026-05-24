"""skills/templates/search_select_play.py"""
from skills.step_runner import StepRunnerSkill


class SearchSelectPlaySkill(StepRunnerSkill):
    name = "search_select_play"
    description = "Searches, selects, and plays"
    STEPS = ['search', 'select', 'play']
