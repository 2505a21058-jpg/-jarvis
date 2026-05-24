"""Compatibility wrapper for the legacy open-and-type skill name."""

from skills.templates.open_type import OpenTypeSkill


class OpenAndTypeSkill(OpenTypeSkill):
    name = "open_and_type"
    description = "Opens an application then types specified text into it"
    timeout_seconds = 25.0
