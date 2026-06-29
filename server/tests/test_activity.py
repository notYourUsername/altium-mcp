"""Tier A (no-Altium) tests for the write-action activity log."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))

from activity import append_activity, format_activity_line  # noqa: E402


def test_read_command_is_not_logged():
    assert format_activity_line("get_bom", {}, {"success": True}) is None
    assert format_activity_line("get_pcb_rules", {}, {"success": True}) is None


def test_write_command_ok_line():
    line = format_activity_line(
        "create_clearance_rule",
        {"rule_name": "R1", "gap_mils": 12},
        {"success": True, "result": {"success": True}},
        now="2026-01-01 00:00:00",
    )
    assert line is not None
    assert "create_clearance_rule" in line
    assert line.find("OK") != -1
    assert "rule_name" in line and "gap_mils" in line


def test_write_command_error_line():
    line = format_activity_line(
        "run_drc", {}, {"success": False, "error": "boom"}, now="t"
    )
    assert "ERR" in line and "boom" in line


def test_append_only_writes_for_write_commands(tmp_path):
    log = tmp_path / "mcp_activity.log"
    assert append_activity(log, "get_pcb_rules", {}, {"success": True}) is False
    assert not log.exists()
    assert append_activity(log, "move_components", {"x_offset": 5}, {"success": True}) is True
    assert log.read_text(encoding="utf-8").count("move_components") == 1
