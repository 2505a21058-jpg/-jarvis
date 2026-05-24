"""skills/templates/open_search_play_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchPlayTypeSkill(StepRunnerSkill):
    name = "open_search_play_type"
    description = "Opens, searches, plays, and types"
    STEPS = ['open', 'search', 'play', 'type']
