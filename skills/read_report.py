"""
skills/read_report.py
Extracts and summarizes text from PDF or text files.
Optional dependency: pip install pdfplumber
"""

from __future__ import annotations

import logging
import os

from skills.base import SkillBase, SkillResult


logger = logging.getLogger("jarvis.skills.read_report")

_MAX_DIRECT_CHARS = 1000


class ReadReportSkill(SkillBase):
    name = "read_report"
    description = "Reads and summarizes a PDF or text file from disk"
    timeout_seconds = 30.0

    def execute(self, params: dict, state) -> SkillResult:
        _ = state
        file_path = str(params.get("path", "")).strip()

        if not file_path:
            return SkillResult(success=False, output=None, error="No file path specified")
        if not os.path.exists(file_path):
            return SkillResult(success=False, output=None, error=f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".pdf":
                content = self._read_pdf(file_path)
            elif ext in (".txt", ".md", ".rst", ".log", ".csv"):
                content = self._read_text(file_path)
            else:
                return SkillResult(
                    success=False,
                    output=None,
                    error=f"Unsupported file type: {ext}. Supported: pdf, txt, md, csv",
                )

            if not content.strip():
                return SkillResult(success=False, output=None, error="File appears to be empty")

            if len(content) > _MAX_DIRECT_CHARS:
                summary = self._summarize(content)
                return SkillResult(
                    success=True,
                    output=f"[Summary of {os.path.basename(file_path)}]\n{summary}",
                )

            return SkillResult(success=True, output=content)

        except Exception as exc:
            logger.error("read_report error: %s", exc)
            return SkillResult(success=False, output=None, error=str(exc))

    def _read_pdf(self, path: str) -> str:
        try:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            logger.warning("pdfplumber not installed. Run: pip install pdfplumber")
            return self._read_text(path)

    def _read_text(self, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()

    def _summarize(self, content: str) -> str:
        try:
            from models.llm import call_llm

            return call_llm(
                system="You are a document summarizer. Be concise and factual.",
                user="Summarize this document in 3-5 sentences:\n\n" + content[:4000],
                temperature=0.3,
                max_tokens=300,
            )
        except Exception as exc:
            logger.warning("Summarization failed: %s", exc)
            return content[:_MAX_DIRECT_CHARS] + "... [truncated]"
