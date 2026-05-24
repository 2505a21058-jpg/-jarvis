"""skills/templates/open_search_select_play.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectPlaySkill(StepRunnerSkill):
    name = "open_search_select_play"
    description = "Opens, searches, selects, and plays"
    STEPS = ['open', 'search', 'select', 'play']
