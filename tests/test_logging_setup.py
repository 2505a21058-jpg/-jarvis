from __future__ import annotations

import json
import logging

from utils.logging_setup import setup_logging


def test_setup_logging_writes_json_lines_file(tmp_path):
    log_path = tmp_path / "jarvis.log"

    setup_logging(console_level="CRITICAL", log_file=str(log_path), file_level="INFO")
    logging.getLogger("test.logging").info("works")

    for handler in logging.getLogger().handlers:
        handler.flush()

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert any(record["logger"] == "test.logging" and record["msg"] == "works" for record in records)
    assert records[-1]["level"] == "INFO"
    assert "ts" in records[-1]
    assert "module" in records[-1]
    assert "line" in records[-1]


def test_setup_logging_replaces_prior_jarvis_handlers(tmp_path):
    first_path = tmp_path / "first.log"
    second_path = tmp_path / "second.log"

    setup_logging(console_level="CRITICAL", log_file=str(first_path), file_level="INFO")
    setup_logging(console_level="CRITICAL", log_file=str(second_path), file_level="INFO")
    logging.getLogger("test.logging").info("after reset")

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert "after reset" not in first_path.read_text(encoding="utf-8")
    assert "after reset" in second_path.read_text(encoding="utf-8")
