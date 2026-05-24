"""skills/templates/open_search_select_play_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectPlaySelectSkill(StepRunnerSkill):
    name = "open_search_select_play_select"
    description = "Opens, searches, selects, plays, and selects"
    STEPS = ['open', 'search', 'select', 'play', 'select']
