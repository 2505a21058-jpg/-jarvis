"""skills/templates/open_search_scroll.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchScrollSkill(StepRunnerSkill):
    name = "open_search_scroll"
    description = "Opens, searches, and scrolls results"
    STEPS = ['open', 'search', 'scroll']
