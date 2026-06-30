"""
Fab-profile loading + DFM evaluation (pure Python, no Altium deps).

A fab profile (fab_profiles/<name>.json) captures one manufacturer's hard minimum
capabilities. apply_fab_profile seeds the board's design rules from these limits;
check_against_fab compares the board against them.

To keep the verdict logic unit-testable offline, the DelphiScript side only *measures*
the board (smallest track, smallest via hole, current rule minimums, ...) and this module
decides OK / WARN / VIOLATION. All values are in millimetres.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REQUIRED_RULE_KEYS = ["min_trace_mm", "min_space_mm", "min_via_diameter_mm",
                      "min_via_drill_mm", "min_annular_ring_mm", "min_hole_to_hole_mm"]

# Small tolerance (mm) so floating dust / rounding doesn't trip a violation (~0.1 mil).
EPS = 0.0025


def load_profile(path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = data.get("rules")
    if not isinstance(rules, dict):
        raise ValueError("fab profile missing 'rules' object")
    missing = [k for k in REQUIRED_RULE_KEYS if k not in rules]
    if missing:
        raise ValueError(f"fab profile rules missing keys: {missing}")
    return data


def find_profile(fab_profiles_dir, name: str) -> Optional[Path]:
    """Match a profile by fab name or file stem, case-insensitively."""
    d = Path(fab_profiles_dir)
    want = name.strip().lower()
    for p in d.glob("*.json"):
        if p.name == "fab_profile.schema.json":
            continue
        if p.stem.lower() == want:
            return p
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("fab", "").lower() == want:
                return p
        except Exception:
            continue
    return None


# (limit_key, measurement_key, human label). A finding is a VIOLATION when the measured
# value is below the fab's minimum by more than EPS.
GEOMETRY_CHECKS = [
    ("min_trace_mm", "min_track_width_mm", "Track width"),
    ("min_via_drill_mm", "min_via_hole_mm", "Via drill"),
    ("min_via_diameter_mm", "min_via_pad_mm", "Via pad diameter"),
    ("min_annular_ring_mm", "min_via_annular_mm", "Via annular ring"),
    ("min_via_drill_mm", "min_pad_hole_mm", "Pad hole"),
    ("min_annular_ring_mm", "min_pad_annular_mm", "Pad annular ring"),
    ("min_hole_to_hole_mm", "min_hole_to_hole_mm", "Hole-to-hole spacing"),
    ("copper_to_edge_mm", "min_copper_to_edge_mm", "Copper-to-edge clearance"),
]

# Rule-floor checks: the board's design-rule minimum should not allow tighter than the fab.
RULE_CHECKS = [
    ("min_trace_mm", "rule_min_width_mm", "Min-width rule floor"),
    ("min_space_mm", "rule_min_clearance_mm", "Clearance rule floor"),
    ("min_via_drill_mm", "rule_via_hole_mm", "Via-rule hole floor"),
    ("min_via_diameter_mm", "rule_via_pad_mm", "Via-rule pad floor"),
    ("min_hole_to_hole_mm", "rule_hole_to_hole_mm", "Hole-to-hole rule floor"),
]


def _mm_to_mil(mm: float) -> float:
    return round(mm / 0.0254, 2)


def _finding(label, limit_mm, actual_mm, kind):
    ok = actual_mm is None or actual_mm >= (limit_mm - EPS)
    return {
        "check": label,
        "kind": kind,  # "geometry" or "rule"
        "limit_mm": round(limit_mm, 4),
        "limit_mil": _mm_to_mil(limit_mm),
        "actual_mm": None if actual_mm is None else round(actual_mm, 4),
        "actual_mil": None if actual_mm is None else _mm_to_mil(actual_mm),
        "status": "OK" if ok else "VIOLATION",
    }


def evaluate_dfm(profile: Dict[str, Any], measurement: Dict[str, Any]) -> Dict[str, Any]:
    """Compare a board measurement (mm) against the fab profile. Returns findings + summary."""
    rules = profile["rules"]
    findings: List[Dict[str, Any]] = []

    for limit_key, meas_key, label in GEOMETRY_CHECKS:
        if limit_key in rules and meas_key in measurement and measurement[meas_key] is not None:
            findings.append(_finding(label, rules[limit_key], measurement[meas_key], "geometry"))

    for limit_key, meas_key, label in RULE_CHECKS:
        if limit_key in rules and meas_key in measurement and measurement[meas_key] is not None:
            findings.append(_finding(label, rules[limit_key], measurement[meas_key], "rule"))

    violations = [f for f in findings if f["status"] == "VIOLATION"]
    return {
        "fab": profile.get("fab"),
        "verified": profile.get("verified", False),
        "total_checks": len(findings),
        "violation_count": len(violations),
        "passed": len(violations) == 0,
        "findings": findings,
    }
