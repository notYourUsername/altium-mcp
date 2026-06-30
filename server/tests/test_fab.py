"""Tier A (no-Altium) tests for fab-profile loading + DFM evaluation."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
FP_DIR = SERVER / "fab_profiles"
sys.path.insert(0, str(SERVER))

from fab import evaluate_dfm, find_profile, load_profile  # noqa: E402


def test_pcbway_profile_loads():
    prof = load_profile(FP_DIR / "pcbway.json")
    assert prof["fab"] == "PCBWay"
    assert prof["verified"] is False  # must not claim verified until checked
    assert prof["rules"]["min_trace_mm"] == 0.0762


def test_find_profile_by_name_and_stem():
    assert find_profile(FP_DIR, "PCBWay") is not None
    assert find_profile(FP_DIR, "pcbway") is not None
    assert find_profile(FP_DIR, "nope-fab") is None


def test_missing_required_keys_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"fab":"X","rules":{"min_trace_mm":0.1}}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_profile(bad)


def _prof():
    return load_profile(FP_DIR / "pcbway.json")


def test_clean_board_passes():
    # Everything comfortably above PCBWay minimums.
    meas = {
        "min_track_width_mm": 0.20, "min_via_hole_mm": 0.30, "min_via_pad_mm": 0.60,
        "min_via_annular_mm": 0.15, "min_pad_hole_mm": 0.40, "min_pad_annular_mm": 0.20,
        "rule_min_width_mm": 0.15, "rule_min_clearance_mm": 0.15,
        "rule_via_hole_mm": 0.30, "rule_via_pad_mm": 0.60, "rule_hole_to_hole_mm": 0.45,
    }
    res = evaluate_dfm(_prof(), meas)
    assert res["passed"] is True
    assert res["violation_count"] == 0
    assert res["total_checks"] == 11


def test_thin_track_and_small_drill_flagged():
    meas = {
        "min_track_width_mm": 0.05,   # below 0.0762 -> violation
        "min_via_hole_mm": 0.15,      # below 0.20 -> violation
        "min_via_pad_mm": 0.60,
        "min_via_annular_mm": 0.10,   # below 0.15 -> violation
    }
    res = evaluate_dfm(_prof(), meas)
    assert res["passed"] is False
    viol = {f["check"] for f in res["findings"] if f["status"] == "VIOLATION"}
    assert "Track width" in viol
    assert "Via drill" in viol
    assert "Via annular ring" in viol


def test_eps_does_not_false_flag_exact_minimum():
    # A track exactly at the limit must not be a violation.
    res = evaluate_dfm(_prof(), {"min_track_width_mm": 0.0762})
    assert res["violation_count"] == 0


def test_missing_measurements_skipped():
    res = evaluate_dfm(_prof(), {"min_track_width_mm": 0.20})
    assert res["total_checks"] == 1


def test_hole_to_hole_and_copper_to_edge_clean_pass():
    # PCBWay: min_hole_to_hole_mm=0.5, copper_to_edge_mm=0.2. Both comfortably above.
    meas = {"min_hole_to_hole_mm": 0.80, "min_copper_to_edge_mm": 0.50}
    res = evaluate_dfm(_prof(), meas)
    assert res["passed"] is True
    assert res["violation_count"] == 0
    checks = {f["check"] for f in res["findings"]}
    assert "Hole-to-hole spacing" in checks
    assert "Copper-to-edge clearance" in checks


def test_hole_to_hole_and_copper_to_edge_violation():
    # Below PCBWay's 0.5mm hole-to-hole and 0.2mm copper-to-edge minimums.
    meas = {"min_hole_to_hole_mm": 0.25, "min_copper_to_edge_mm": 0.10}
    res = evaluate_dfm(_prof(), meas)
    assert res["passed"] is False
    viol = {f["check"] for f in res["findings"] if f["status"] == "VIOLATION"}
    assert "Hole-to-hole spacing" in viol
    assert "Copper-to-edge clearance" in viol
