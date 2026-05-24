"""skills/templates/open_tab_search_play_select.py"""
from skills.step_runner import StepRunnerSkill


class OpenTabSearchPlaySelectSkill(StepRunnerSkill):
    name = "open_tab_search_play_select"
    description = "Opens, opens tab, searches, plays, and selects"
    STEPS = ['open', 'tab', 'search', 'play', 'select']
