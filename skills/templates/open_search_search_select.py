"""skills/templates/open_search_search_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSearchSelectSkill(StepRunnerSkill):
    name = "open_search_search_select"
    description = "Opens, searches twice, and selects"
    STEPS = ['open', 'search', 'search', 'select']
