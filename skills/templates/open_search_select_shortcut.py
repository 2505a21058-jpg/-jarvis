"""skills/templates/open_search_select_shortcut.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectShortcutSkill(StepRunnerSkill):
    name = "open_search_select_shortcut"
    description = "Opens, searches, selects, and executes shortcut"
    STEPS = ['open', 'search', 'select', 'shortcut']
