"""skills/templates/open_search_search_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSearchSelectSelectSkill(StepRunnerSkill):
    name = "open_search_search_select_select"
    description = "Opens, searches twice, and selects twice"
    STEPS = ['open', 'search', 'search', 'select', 'select']
