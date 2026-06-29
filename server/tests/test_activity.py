"""Tier A (no-Altium) tests for the write-action activity log + classification."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))

from activity import append_activity, format_activity_line, is_write_command  # noqa: E402

OK = {"success": True}


# --- classification (fail-safe) ---------------------------------------------

READS = [
    "get_bom", "get_pcb_rules", "get_board_info", "get_all_component_data",
    "get_drc_violations", "get_schematic_nets", "search_library_symbol",
    "take_view_screenshot", "get_server_status",
]

WRITES = [
    "create_clearance_rule", "update_clearance_rule", "create_width_rule",
    "create_via_rule", "run_drc", "create_net_class", "create_pcb_footprint",
    "create_schematic_symbol", "move_components", "set_component_position",
    "set_pcb_layer_visibility", "layout_duplicator_apply", "run_output_jobs",
]


@pytest.mark.parametrize("cmd", READS)
def test_reads_not_logged(cmd):
    assert is_write_command(cmd) is False
    assert format_activity_line(cmd, {}, OK) is None


@pytest.mark.parametrize("cmd", WRITES)
def test_writes_logged(cmd):
    assert is_write_command(cmd) is True
    assert format_activity_line(cmd, {}, OK) is not None


def test_unknown_write_is_failsafe_logged():
    # A brand-new write tool that nobody added to any allowlist must still log.
    assert is_write_command("frobnicate_board") is True
    assert format_activity_line("frobnicate_board", {"x": 1}, OK) is not None


# --- the specific regression: these three used to silently miss the log -----

@pytest.mark.parametrize("cmd", ["create_width_rule", "create_via_rule", "update_clearance_rule"])
def test_regression_previously_unlogged_writes_now_log(cmd):
    line = format_activity_line(cmd, {"rule_name": "X"}, OK, now="2026-06-29 19:13:41")
    assert line is not None
    assert cmd in line and "OK" in line


# --- format + summary -------------------------------------------------------

def test_format_matches_existing_lines():
    line = format_activity_line(
        "create_clearance_rule",
        {"gap_mils": 20.0, "rule_name": "HV", "scope1": "InNet('HV')", "scope2": "All"},
        OK,
        now="2026-06-29 19:13:41",
    )
    assert line == (
        "[2026-06-29 19:13:41] OK  create_clearance_rule "
        "params={\"gap_mils\": 20.0, \"rule_name\": \"HV\", "
        "\"scope1\": \"InNet('HV')\", \"scope2\": \"All\"}"
    )


def test_error_line_marked_err():
    line = format_activity_line("run_drc", {}, {"success": False, "error": "boom"}, now="t")
    assert "ERR" in line and "boom" in line


# --- append behaviour -------------------------------------------------------

def test_append_only_writes_for_write_commands(tmp_path):
    log = tmp_path / "mcp_activity.log"
    assert append_activity(log, "get_pcb_rules", {}, OK) is False
    assert not log.exists()
    assert append_activity(log, "create_width_rule", {"rule_name": "W"}, OK) is True
    assert append_activity(log, "create_via_rule", {"rule_name": "V"}, OK) is True
    contents = log.read_text(encoding="utf-8")
    assert contents.count("create_width_rule") == 1
    assert contents.count("create_via_rule") == 1
