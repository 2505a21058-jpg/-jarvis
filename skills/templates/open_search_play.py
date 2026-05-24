"""skills/templates/open_search_play.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchPlaySkill(StepRunnerSkill):
    name = "open_search_play"
    description = "Opens, searches, and plays content"
    STEPS = ['open', 'search', 'play']
