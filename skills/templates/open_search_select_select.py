"""skills/templates/open_search_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectSelectSkill(StepRunnerSkill):
    name = "open_search_select_select"
    description = "Opens, searches, and selects twice"
    STEPS = ['open', 'search', 'select', 'select']
