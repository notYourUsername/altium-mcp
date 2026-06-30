"""
Impedance-driven trace-width estimation (pure Python, no Altium deps).

This module implements accepted closed-form transmission-line models to estimate
the characteristic impedance Z0 of a single-ended PCB trace, and to solve for the
trace width that yields a target Z0.

IMPORTANT - THESE ARE ESTIMATES
    The analytic models below are engineering approximations. Real impedance depends
    on etch trapezoid shape, solder-mask coating, glass-weave/Dk anisotropy, copper
    roughness and manufacturing tolerances. Expect roughly +/-5-10% disagreement
    versus a proper 2D field solver (e.g. Polar SI9000, Saturn PCB, an EM tool) or
    the fabricator's controlled-impedance calculator. ALWAYS confirm any width these
    functions return against a field solver or your fab's stack-up calculator before
    committing to a controlled-impedance design.

Units: all public functions take/return millimetres (mm). A mil convenience value
(1 mil = 0.0254 mm) is included in solver output.

Models / sources
    - Microstrip (surface trace, dielectric on one side, air above):
        Hammerstad & Jensen accurate static model, as collected in
        B. C. Wadell, "Transmission Line Design Handbook", Artech House, 1991,
        chapter 3 (microstrip). The effective permittivity + impedance equations
        used here are the Hammerstad-Jensen forms reproduced widely (e.g. Wadell
        eq. for eps_eff(u) and Z0(u), with u = w/h).
        A finite-copper-thickness correction (effective width widening) follows the
        Hammerstad-Jensen / IPC-2141A treatment (delta-w from trace thickness t).
    - Stripline (buried trace, dielectric on both sides, symmetric):
        Closed-form from IPC-2141A "Design Guide for High-Speed Controlled Impedance
        Circuit Boards", sec. 4.2.2 (symmetric stripline), with the standard
        thickness correction. Cross-checked against Wadell ch. 3 (stripline).

These references are textbook-standard; the in-line comments cite the specific form.
"""
from __future__ import annotations

import math
from typing import Dict

MM_PER_MIL = 0.0254
_FREE_SPACE_Z = 376.730313668  # impedance of free space, ohms (mu0*c)


def mm_to_mil(mm: float) -> float:
    return mm / MM_PER_MIL


def mil_to_mm(mil: float) -> float:
    return mil * MM_PER_MIL


# ---------------------------------------------------------------------------
# Microstrip
# ---------------------------------------------------------------------------
def microstrip_z0(w_mm: float, h_mm: float, t_mm: float, er: float) -> float:
    """
    Single-ended microstrip characteristic impedance Z0 (ohms), ESTIMATE.

    Hammerstad-Jensen accurate model (Wadell, "Transmission Line Design Handbook",
    1991, ch.3). Finite conductor thickness t is folded in via the Hammerstad-Jensen
    effective-width correction (also given in IPC-2141A).

    Args:
        w_mm: trace width (mm)
        h_mm: dielectric height between trace and reference plane (mm)
        t_mm: copper thickness (mm); set 0 to ignore the thickness correction
        er:   relative permittivity (Dk) of the dielectric

    Returns:
        Estimated Z0 in ohms. Approximate to ~+/-5-10% vs a 2D field solver.
    """
    if w_mm <= 0 or h_mm <= 0:
        raise ValueError("w_mm and h_mm must be positive")
    if er < 1:
        raise ValueError("er must be >= 1")

    # --- Finite-thickness correction: widen w by delta_w (Hammerstad-Jensen / IPC-2141A).
    # delta_w accounts for the extra coupling from the trace's vertical sidewalls.
    w_eff = w_mm
    if t_mm > 0:
        t = t_mm
        # Hammerstad-Jensen thickness term (Wadell ch.3): use the wide-trace form
        # delta_w = (t/pi) * ln(1 + 4*e / ( (t/h) * coth(sqrt(6.517*w/h))^2 )).
        # A simpler, widely-used IPC-2141A approximation is adequate at our accuracy:
        #   delta_w = (t/pi) * (1 + ln(2*h/t))      for w/h >= 1/(2*pi)
        delta_w = (t / math.pi) * (1.0 + math.log(2.0 * h_mm / t))
        w_eff = w_mm + delta_w

    u = w_eff / h_mm  # normalized width

    # --- Effective relative permittivity, Hammerstad-Jensen (Wadell ch.3).
    a = (1.0
         + (1.0 / 49.0) * math.log((u ** 4 + (u / 52.0) ** 2) / (u ** 4 + 0.432))
         + (1.0 / 18.7) * math.log(1.0 + (u / 18.1) ** 3))
    b = 0.564 * ((er - 0.9) / (er + 3.0)) ** 0.053
    eps_eff = (er + 1.0) / 2.0 + ((er - 1.0) / 2.0) * (1.0 + 10.0 / u) ** (-a * b)

    # --- Characteristic impedance of the equivalent air microstrip, Hammerstad-Jensen.
    f = 6.0 + (2.0 * math.pi - 6.0) * math.exp(-((30.666 / u) ** 0.7528))
    z01 = (_FREE_SPACE_Z / (2.0 * math.pi)) * math.log(
        f / u + math.sqrt(1.0 + (2.0 / u) ** 2))

    # Fill with the dielectric.
    return z01 / math.sqrt(eps_eff)


# ---------------------------------------------------------------------------
# Stripline (symmetric, centred between two planes)
# ---------------------------------------------------------------------------
def stripline_z0(w_mm: float, h_mm: float, t_mm: float, er: float) -> float:
    """
    Single-ended symmetric stripline characteristic impedance Z0 (ohms), ESTIMATE.

    IPC-2141A symmetric-stripline closed form (sec. 4.2.2), cross-checked vs Wadell
    ch.3. Here h_mm is the TOTAL plane-to-plane dielectric height (b), with the trace
    centred, so the substrate height on each side is b/2.

    Args:
        w_mm: trace width (mm)
        h_mm: total dielectric height between the two reference planes (mm)
        t_mm: copper thickness (mm)
        er:   relative permittivity (Dk)

    Returns:
        Estimated Z0 in ohms. Approximate to ~+/-5-10% vs a 2D field solver.
    """
    if w_mm <= 0 or h_mm <= 0:
        raise ValueError("w_mm and h_mm must be positive")
    if er < 1:
        raise ValueError("er must be >= 1")

    b = h_mm  # plane-to-plane spacing
    t = max(t_mm, 0.0)

    # Classic IPC-2141A / Wadell symmetric-stripline narrow-trace form
    # (valid for w/(b - t) < ~0.35, t/b < ~0.25, which covers typical signal traces):
    #   Z0 = (60/sqrt(er)) * ln( 4*b / (0.67*pi*(0.8*w + t)) )
    # The (0.8*w + t) grouping is the standard stripline effective-width term and
    # already folds in conductor thickness t, so it is used directly.
    denom = 0.67 * math.pi * (0.8 * w_mm + t)
    if denom <= 0:
        raise ValueError("invalid geometry for stripline")
    return (60.0 / math.sqrt(er)) * math.log(4.0 * b / denom)


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------
def _z0_func(mode: str):
    m = mode.strip().lower()
    if m == "microstrip":
        return microstrip_z0
    if m == "stripline":
        return stripline_z0
    raise ValueError(f"unknown mode {mode!r}; expected 'microstrip' or 'stripline'")


def solve_width_for_impedance(target_ohms: float, h_mm: float, er: float,
                              t_mm: float = 0.035, mode: str = "microstrip",
                              tol_ohms: float = 0.01, max_iter: int = 100) -> Dict[str, float]:
    """
    Solve for the trace width (mm) giving a target single-ended Z0, by bisection.

    Z0 decreases monotonically with width (wider trace -> lower impedance), so a
    bisection on width is well-behaved. Result is an ESTIMATE - confirm against a
    2D field solver or the fab's controlled-impedance calculator.

    Args:
        target_ohms: desired characteristic impedance (ohms)
        h_mm:        dielectric height (mm). For stripline this is the total
                     plane-to-plane spacing.
        er:          relative permittivity (Dk)
        t_mm:        copper thickness (mm), default 0.035 (1 oz).
        mode:        "microstrip" or "stripline".

    Returns:
        dict with width_mm, width_mil, z0_check_ohms (Z0 back-computed at the solved
        width), target_ohms, iterations, converged (bool), and a note string.
    """
    if target_ohms <= 0:
        raise ValueError("target_ohms must be positive")
    z0 = _z0_func(mode)

    # Bracket the width. Narrow -> high Z0, wide -> low Z0.
    w_lo = 1e-4 * h_mm + 1e-4   # very narrow (high Z0)
    w_hi = 50.0 * h_mm + 50.0   # very wide (low Z0)

    z_lo = z0(w_lo, h_mm, t_mm, er)  # high impedance
    z_hi = z0(w_hi, h_mm, t_mm, er)  # low impedance

    # If target is outside the achievable range, clamp to the nearest bracket end
    # and report it (do not silently pretend we hit it).
    note = ("ESTIMATE only (+/-~5-10% vs a 2D field solver). Confirm against a field "
            "solver or your fab's controlled-impedance calculator before use.")
    if target_ohms >= z_lo:
        w = w_lo
        return {"width_mm": round(w, 5), "width_mil": round(mm_to_mil(w), 4),
                "z0_check_ohms": round(z0(w, h_mm, t_mm, er), 3),
                "target_ohms": target_ohms, "iterations": 0, "converged": False,
                "note": "Target Z0 too high for this stackup even at minimum width. " + note}
    if target_ohms <= z_hi:
        w = w_hi
        return {"width_mm": round(w, 5), "width_mil": round(mm_to_mil(w), 4),
                "z0_check_ohms": round(z0(w, h_mm, t_mm, er), 3),
                "target_ohms": target_ohms, "iterations": 0, "converged": False,
                "note": "Target Z0 too low for this stackup even at maximum width. " + note}

    converged = False
    i = 0
    for i in range(1, max_iter + 1):
        w_mid = 0.5 * (w_lo + w_hi)
        z_mid = z0(w_mid, h_mm, t_mm, er)
        if abs(z_mid - target_ohms) <= tol_ohms:
            converged = True
            break
        # Z0 decreases with width: if we're above target, need wider trace.
        if z_mid > target_ohms:
            w_lo = w_mid
        else:
            w_hi = w_mid
    w = 0.5 * (w_lo + w_hi)
    z_final = z0(w, h_mm, t_mm, er)
    return {"width_mm": round(w, 5), "width_mil": round(mm_to_mil(w), 4),
            "z0_check_ohms": round(z_final, 3), "target_ohms": target_ohms,
            "iterations": i, "converged": converged, "note": note}
