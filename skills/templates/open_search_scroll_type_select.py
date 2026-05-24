"""skills/templates/open_search_scroll_type_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchScrollTypeSelectSkill(StepRunnerSkill):
    name = "open_search_scroll_type_select"
    description = "Opens, searches, scrolls, types, and selects"
    STEPS = ['open', 'search', 'scroll', 'type', 'select']
