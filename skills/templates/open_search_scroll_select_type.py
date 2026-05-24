"""skills/templates/open_search_scroll_select_type.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchScrollSelectTypeSkill(StepRunnerSkill):
    name = "open_search_scroll_select_type"
    description = "Opens, searches, scrolls, selects, and types"
    STEPS = ['open', 'search', 'scroll', 'select', 'type']
