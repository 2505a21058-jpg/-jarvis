from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from skills.read_report import ReadReportSkill


@pytest.fixture
def skill():
    return ReadReportSkill()


def test_reads_plain_text_file(tmp_path, state, skill):
    file = tmp_path / "notes.txt"
    file.write_text("hello world", encoding="utf-8")
    result = skill.execute({"path": str(file)}, state)
    assert result.success
    assert "hello world" in result.output


def test_reads_pdf_file(tmp_path, state, skill):
    file = tmp_path / "doc.pdf"
    file.write_text("dummy", encoding="utf-8")
    with patch("pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PDF text content"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdf
        result = skill.execute({"path": str(file)}, state)
    assert result.success
    assert "PDF text content" in result.output


def test_missing_file_returns_error(state, skill):
    result = skill.execute({"path": "/nonexistent/path.txt"}, state)
    assert not result.success


def test_empty_file_returns_error(state, skill):
    with patch("os.path.exists", return_value=True):
        with patch("skills.read_report.ReadReportSkill._read_text", return_value=""):
            result = skill.execute({"path": "empty.txt"}, state)
    assert not result.success


def test_large_file_is_summarized(tmp_path, state, skill):
    file = tmp_path / "large.txt"
    file.write_text("word " * 500, encoding="utf-8")
    with patch("models.llm.call_llm", return_value="summarized"):
        result = skill.execute({"path": str(file)}, state)
    assert result.success
    assert "Summary" in result.output
