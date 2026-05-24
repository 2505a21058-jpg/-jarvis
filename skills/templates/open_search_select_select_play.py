"""skills/templates/open_search_select_select_play.py"""
from skills.step_runner import StepRunnerSkill


class OpenSearchSelectSelectPlaySkill(StepRunnerSkill):
    name = "open_search_select_select_play"
    description = "Opens, searches, selects twice, and plays"
    STEPS = ['open', 'search', 'select', 'select', 'play']
