from __future__ import annotations

import os
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


def test_rejects_start_path_outside_allowed_roots(tmp_path, monkeypatch, state, skill):
    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    monkeypatch.setenv("JARVIS_ALLOWED_FILE_ROOTS", str(allowed_root))

    with patch("skills.system_search._search_filesystem") as mock_search:
        result = skill.execute(
            {"query": "target", "start_path": str(blocked_root)},
            state,
        )

    assert not result.success
    assert "outside allowed file roots" in (result.error or "").lower()
    mock_search.assert_not_called()


def test_default_search_uses_configured_allowed_roots(tmp_path, monkeypatch, state, skill):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("JARVIS_ALLOWED_FILE_ROOTS", os.pathsep.join([str(first), str(second)]))

    with patch("skills.system_search._search_filesystem", return_value=[]) as mock_search:
        result = skill.execute({"query": "target"}, state)

    assert result.success
    assert mock_search.call_args.kwargs["start_paths"] == [str(first.resolve()), str(second.resolve())]


def test_empty_query_returns_error(state, skill):
    result = skill.execute({"query": ""}, state)
    assert not result.success
