"""skills/templates/open_search_select_scroll.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectScrollSkill(StepRunnerSkill):
    name = "open_search_select_scroll"
    description = "Opens, searches, selects, and scrolls"
    STEPS = ['open', 'search', 'select', 'scroll']
