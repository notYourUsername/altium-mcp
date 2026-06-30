"""Tier A (no-Altium) tests for high-speed signal-profile loading + rule building."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
SP_DIR = SERVER / "signal_profiles"
sys.path.insert(0, str(SERVER))

from signalrules import (  # noqa: E402
    build_rule_commands,
    find_profile,
    list_profiles,
    load_profile,
)


def test_usb2_profile_loads():
    prof = load_profile(SP_DIR / "usb2.json")
    assert prof["profile"] == "usb2"
    assert prof["impedance_ohms"] == [85.0, 95.0]
    assert prof["diff_gap_mils"] == 7.5


def test_can_profile_loads():
    prof = load_profile(SP_DIR / "can.json")
    assert prof["profile"] == "can"
    assert prof["impedance_ohms"][0] == 108.0
    assert prof["impedance_ohms"][1] == 132.0


def test_find_profile_by_name_and_stem():
    assert find_profile(SP_DIR, "usb2") is not None
    assert find_profile(SP_DIR, "USB2") is not None
    assert find_profile(SP_DIR, "can") is not None
    assert find_profile(SP_DIR, "nope-bus") is None


def test_list_profiles_skips_schema():
    profiles = list_profiles(SP_DIR)
    names = {p["profile"] for p in profiles}
    assert "usb2" in names
    assert "can" in names
    assert all("schema" not in p["file"] for p in profiles)


def test_missing_required_keys_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"profile":"x","width_mils":8}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_profile(bad)


def test_bad_impedance_pair_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "profile": "x", "width_mils": 8, "diff_gap_mils": 7,
        "impedance_ohms": [90], "length_tolerance_mils": 5,
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        load_profile(bad)


def test_impedance_min_gt_max_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "profile": "x", "width_mils": 8, "diff_gap_mils": 7,
        "impedance_ohms": [95, 85], "length_tolerance_mils": 5,
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        load_profile(bad)


def test_build_rule_commands_shape_and_scope():
    prof = load_profile(SP_DIR / "usb2.json")
    cmds = build_rule_commands(prof, "USB")
    assert len(cmds) == 4
    kinds = [c["command"] for c in cmds]
    assert kinds == [
        "create_width_rule",
        "create_diff_pair_rule",
        "create_impedance_rule",
        "create_length_match_rule",
    ]
    for c in cmds:
        assert c["params"]["scope1"] == "InNetClass('USB')"

    width_cmd = cmds[0]["params"]
    assert width_cmd["preferred_mils"] == 8.0
    assert width_cmd["min_mils"] == pytest.approx(6.0)
    assert width_cmd["max_mils"] == pytest.approx(10.0)
    assert width_cmd["rule_name"] == "Width_USB"

    imp_cmd = cmds[2]["params"]
    assert imp_cmd["min_ohms"] == 85.0
    assert imp_cmd["max_ohms"] == 95.0

    lm_cmd = cmds[3]["params"]
    assert lm_cmd["tolerance_mils"] == 5.0


def test_build_rule_commands_width_floor_nonnegative():
    # A very thin width must not produce a negative/zero min width.
    prof = {
        "profile": "thin", "width_mils": 1.0, "diff_gap_mils": 4.0,
        "impedance_ohms": [50.0, 55.0], "length_tolerance_mils": 2.0,
    }
    cmds = build_rule_commands(prof, "X")
    assert cmds[0]["params"]["min_mils"] >= 0.1


def test_shipped_profiles_validate_against_schema():
    schema_path = SP_DIR / "signal_profile.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema = pytest.importorskip("jsonschema")
    for p in SP_DIR.glob("*.json"):
        if p.name == schema_path.name:
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        jsonschema.validate(instance=data, schema=schema)
