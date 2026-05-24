"""Skill to fetch and summarize any URL."""

from __future__ import annotations

from skills.base import SkillBase, SkillResult


class ReadUrlSkill(SkillBase):
    name = "read_url"
    description = "Fetch a URL and summarize its content"
    timeout_seconds = 30.0

    def execute(self, params: dict, state) -> SkillResult:
        from internet.fetch import fetch_page
        from models.llm import call_llm

        url = str(params.get("url") or params.get("query") or "").strip()
        topic = str(params.get("topic") or "").strip()

        if not url and topic:
            url = topic
        if not url:
            return SkillResult(
                success=False, output="", error="Please provide a URL to read.",
                skill_name=self.name,
            )

        # Normalize: prepend https:// if missing
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
            params = {**params, "url": url}

        content = fetch_page(url)
        if not content or len(content) < 80:
            return SkillResult(
                success=False,
                output="",
                error=f"Could not read content from {url}. The page may be inaccessible or non-text.",
                skill_name=self.name,
            )

        system = (
            "You are a research assistant. Read the provided webpage content "
            "and give a clear, accurate summary. Include the key points, "
            "main arguments, and notable details. Cite the source URL."
        )
        user = (
            f"URL: {url}\n\n"
            f"Page content:\n{content[:15000]}\n\n"
            "Summarize this page. Include what it's about, key takeaways, and any important details."
        )

        try:
            summary = call_llm(
                system=system,
                user=user,
                temperature=0.2,
                max_tokens=1024,
                timeout=25,
                retries=1,
            )
        except Exception as exc:
            summary = ""

        if summary:
            output = f"## Summary of {url}\n\n{summary.strip()}\n\nSource: {url}"
        else:
            output = f"## Content from {url}\n\n{content[:3000]}\n\nSource: {url}"

        return SkillResult(success=True, output=output, skill_name=self.name)
