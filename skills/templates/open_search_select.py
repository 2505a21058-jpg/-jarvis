"""skills/templates/open_search_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectSkill(StepRunnerSkill):
    name = "open_search_select"
    description = "Opens, searches, and selects a result"
    STEPS = ['open', 'search', 'select']
