"""
High-speed signal-profile loading + validation (pure Python, no Altium deps).

A signal profile (signal_profiles/<name>.json) captures one bus/interface's
high-speed routing targets: single-ended trace width, differential-pair gap,
impedance window, and length-matching tolerance. apply_signal_profile resolves a
profile and seeds a net class's design rules (width, diff-pair, impedance,
matched-length) from these targets.

Mirrors fab.py: this module only loads + validates the profile and builds the
list of rule commands; the DelphiScript side actually creates the rules. All
linear values are in mils; impedance is in ohms.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REQUIRED_KEYS = ["width_mils", "diff_gap_mils", "impedance_ohms", "length_tolerance_mils"]


def load_profile(path) -> Dict[str, Any]:
    """Load + validate a signal profile JSON. Raises ValueError if malformed."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("signal profile must be a JSON object")
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"signal profile missing keys: {missing}")

    for k in ("width_mils", "diff_gap_mils", "length_tolerance_mils"):
        v = data[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(f"signal profile '{k}' must be a number")
        if v < 0:
            raise ValueError(f"signal profile '{k}' must be >= 0")

    imp = data["impedance_ohms"]
    if (not isinstance(imp, (list, tuple)) or len(imp) != 2
            or any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in imp)):
        raise ValueError("signal profile 'impedance_ohms' must be a [min, max] pair of numbers")
    if imp[0] <= 0 or imp[1] <= 0:
        raise ValueError("signal profile 'impedance_ohms' values must be > 0")
    if imp[0] > imp[1]:
        raise ValueError("signal profile 'impedance_ohms' min must be <= max")

    return data


def find_profile(signal_profiles_dir, name: str) -> Optional[Path]:
    """Match a profile by its 'profile' field or file stem, case-insensitively."""
    d = Path(signal_profiles_dir)
    want = name.strip().lower()
    for p in d.glob("*.json"):
        if p.name == "signal_profile.schema.json":
            continue
        if p.stem.lower() == want:
            return p
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("profile", "").lower() == want:
                return p
        except Exception:
            continue
    return None


def list_profiles(signal_profiles_dir) -> List[Dict[str, Any]]:
    """Return a {profile, file} summary for each valid profile (skips the schema)."""
    out: List[Dict[str, Any]] = []
    for p in sorted(Path(signal_profiles_dir).glob("*.json")):
        if p.name == "signal_profile.schema.json":
            continue
        try:
            data = load_profile(p)
            out.append({"profile": data.get("profile", p.stem), "file": p.name})
        except Exception as exc:
            out.append({"profile": p.stem, "file": p.name, "error": str(exc)})
    return out


def build_rule_commands(profile: Dict[str, Any], net_class: str) -> List[Dict[str, Any]]:
    """
    Build the ordered list of Altium rule-creation commands for a net class from a
    profile. Each entry is {"command": <name>, "params": {...}} ready to hand to
    altium_bridge.execute_command. Pure data; issues no side effects.

    Rules created (all scoped to InNetClass('<net_class>')):
      - width rule         (single-ended width target, +/-2 mil window)
      - diff-pair rule     (intra-pair gap + width window)
      - impedance rule     (min/max ohms)
      - length-match rule  (matched-net-length tolerance)
    """
    scope = f"InNetClass('{net_class}')"
    width = float(profile["width_mils"])
    gap = float(profile["diff_gap_mils"])
    imp_min, imp_max = float(profile["impedance_ohms"][0]), float(profile["impedance_ohms"][1])
    tol = float(profile["length_tolerance_mils"])

    # A modest +/- window around the target width so routing has room without
    # drifting off the impedance target.
    w_min = max(0.1, round(width - 2.0, 4))
    w_max = round(width + 2.0, 4)
    prof_name = profile.get("profile", "signal")

    return [
        {
            "command": "create_width_rule",
            "params": {
                "rule_name": f"Width_{net_class}",
                "min_mils": w_min, "max_mils": w_max, "preferred_mils": width,
                "scope1": scope,
            },
        },
        {
            "command": "create_diff_pair_rule",
            "params": {
                "rule_name": f"DiffPair_{net_class}",
                "scope1": scope,
                "gap_mils": gap,
                "min_width_mils": w_min, "max_width_mils": w_max,
                "preferred_width_mils": width,
                "max_uncoupled_mils": tol,
            },
        },
        {
            "command": "create_impedance_rule",
            "params": {
                "rule_name": f"Impedance_{net_class}",
                "scope1": scope, "min_ohms": imp_min, "max_ohms": imp_max,
            },
        },
        {
            "command": "create_length_match_rule",
            "params": {
                "rule_name": f"LengthMatch_{net_class}",
                "scope1": scope, "tolerance_mils": tol,
            },
        },
    ]
