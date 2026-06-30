"""Tier A (no-Altium) tests for the impedance/trace-width estimator.

These check the closed-form models against textbook reference points (within a
tolerance band, because the models are ESTIMATES) and verify the bisection solver
round-trips: Z0(solve_width(Z)) ~= Z.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))

from impedance import (  # noqa: E402
    microstrip_z0,
    stripline_z0,
    solve_width_for_impedance,
    mm_to_mil,
)


# ---------------------------------------------------------------------------
# Reference points (textbook closed-form, thickness neglected for the band that
# the reference value was derived from).
# ---------------------------------------------------------------------------
def test_microstrip_reference_50ohm():
    # er=4.3 (FR-4), h=0.2 mm, t->0: classic Hammerstad-Jensen microstrip puts a
    # 50 ohm line around w ~ 0.36-0.40 mm.
    res = solve_width_for_impedance(50.0, h_mm=0.2, er=4.3, t_mm=0.0, mode="microstrip")
    assert res["converged"] is True
    assert 0.36 <= res["width_mm"] <= 0.40, res


def test_microstrip_z0_monotonic_in_width():
    # Wider trace -> lower impedance (needed for the bisection to be valid).
    z_narrow = microstrip_z0(0.20, 0.2, 0.035, 4.3)
    z_wide = microstrip_z0(0.60, 0.2, 0.035, 4.3)
    assert z_narrow > z_wide


def test_microstrip_thickness_lowers_z0():
    # Finite copper thickness widens the effective trace and lowers Z0.
    z_no_t = microstrip_z0(0.35, 0.2, 0.0, 4.3)
    z_with_t = microstrip_z0(0.35, 0.2, 0.035, 4.3)
    assert z_with_t < z_no_t


def test_stripline_reference_50ohm():
    # Symmetric stripline, er=4.3, total plane-to-plane b=0.5 mm, 1oz copper.
    # IPC-2141A symmetric-stripline form gives a narrow ~50 ohm line; just sanity
    # check it lands in a sane sub-0.3 mm range and round-trips.
    res = solve_width_for_impedance(50.0, h_mm=0.5, er=4.3, t_mm=0.035, mode="stripline")
    assert res["converged"] is True
    assert 0.05 <= res["width_mm"] <= 0.30, res


# ---------------------------------------------------------------------------
# Solver round-trip: Z0(solve_width(Z)) ~= Z
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("target", [40.0, 50.0, 75.0, 90.0])
def test_microstrip_solver_roundtrip(target):
    res = solve_width_for_impedance(target, h_mm=0.2, er=4.3, t_mm=0.035, mode="microstrip")
    assert res["converged"] is True
    assert abs(res["z0_check_ohms"] - target) < 0.5
    # mm/mil consistency
    assert res["width_mil"] == pytest.approx(mm_to_mil(res["width_mm"]), rel=1e-3)


@pytest.mark.parametrize("target", [40.0, 50.0, 60.0])
def test_stripline_solver_roundtrip(target):
    res = solve_width_for_impedance(target, h_mm=0.5, er=4.3, t_mm=0.035, mode="stripline")
    assert res["converged"] is True
    assert abs(res["z0_check_ohms"] - target) < 0.5


def test_unreachable_target_does_not_crash():
    # Absurdly high target -> flagged non-converged, returns minimum-width bracket.
    res = solve_width_for_impedance(500.0, h_mm=0.2, er=4.3, t_mm=0.035, mode="microstrip")
    assert res["converged"] is False
    assert "note" in res


def test_bad_mode_raises():
    with pytest.raises(ValueError):
        solve_width_for_impedance(50.0, h_mm=0.2, er=4.3, mode="coplanar")
