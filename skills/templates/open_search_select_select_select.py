"""skills/templates/open_search_select_select_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectSelectSelectSkill(StepRunnerSkill):
    name = "open_search_select_select_select"
    description = "Opens, searches, and selects three times"
    STEPS = ['open', 'search', 'select', 'select', 'select']
