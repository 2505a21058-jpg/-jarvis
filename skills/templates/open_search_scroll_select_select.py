"""skills/templates/open_search_scroll_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchScrollSelectSelectSkill(StepRunnerSkill):
    name = "open_search_scroll_select_select"
    description = "Opens, searches, scrolls, and selects twice"
    STEPS = ['open', 'search', 'scroll', 'select', 'select']
