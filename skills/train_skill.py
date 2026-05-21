from __future__ import annotations

from skills import SkillBase, SkillResult


class PNRSkill(SkillBase):
    name = "pnr"
    description = "Check Indian Railway PNR status"
    timeout_seconds = 10.0

    def execute(self, params: dict, state) -> SkillResult:
        from skills._train_impl import check_pnr

        pnr = str(params.get("pnr") or params.get("query") or "").strip()
        if not pnr:
            return SkillResult(success=False, output=None, error="Please provide a valid PNR number.", skill_name=self.name)
        result = check_pnr(pnr)
        return SkillResult(success=result is not None, output=result, skill_name=self.name)


class LiveTrainSkill(SkillBase):
    name = "train"
    description = "Get live status of a train in Indian Railway"
    timeout_seconds = 10.0

    def execute(self, params: dict, state) -> SkillResult:
        from skills._train_impl import get_live_train

        train_number = str(params.get("train_number") or params.get("query") or "").strip()
        if not train_number:
            return SkillResult(success=False, output=None, error="Please provide a valid train number.", skill_name=self.name)
        result = get_live_train(train_number)
        return SkillResult(success=result is not None, output=result, skill_name=self.name)
