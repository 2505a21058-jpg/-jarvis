"""skills/templates/open_search_select_type_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectTypeSelectSkill(StepRunnerSkill):
    name = "open_search_select_type_select"
    description = "Opens, searches, selects, types, and selects"
    STEPS = ['open', 'search', 'select', 'type', 'select']
