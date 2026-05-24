"""skills/templates/open_search_select_select_scroll.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectSelectScrollSkill(StepRunnerSkill):
    name = "open_search_select_select_scroll"
    description = "Opens, searches, selects twice, and scrolls"
    STEPS = ['open', 'search', 'select', 'select', 'scroll']
