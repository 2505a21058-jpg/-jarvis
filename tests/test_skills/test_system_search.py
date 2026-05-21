from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.system_search import SystemSearchSkill


@pytest.fixture
def skill():
    return SystemSearchSkill()


def test_finds_file_by_name(state, skill):
    with patch("skills.system_search._search_filesystem") as mock_search:
        mock_search.return_value = [{"name": "target.txt", "path": "/home/target.txt", "type": "file", "size_mb": 0.1}]
        result = skill.execute({"query": "target"}, state)
    assert result.success
    assert "target.txt" in result.output


def test_finds_folder_by_name(state, skill):
    with patch("skills.system_search._search_filesystem") as mock_search:
        mock_search.return_value = [{"name": "my_folder", "path": "/home/my_folder", "type": "folder", "size_mb": None}]
        result = skill.execute({"query": "my_folder"}, state)
    assert result.success
    assert "my_folder" in result.output


def test_no_results_returns_message(state, skill):
    with patch("skills.system_search._search_filesystem", return_value=[]):
        result = skill.execute({"query": "zz_nonexistent_zz"}, state)
    assert result.success


def test_empty_query_returns_error(state, skill):
    result = skill.execute({"query": ""}, state)
    assert not result.success
