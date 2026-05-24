"""skills/templates/open_search.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSkill(StepRunnerSkill):
    name = "open_search"
    description = "Opens an app and searches"
    STEPS = ['open', 'search']
