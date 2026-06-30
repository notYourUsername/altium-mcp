"""
Pure-Python power-decoupling audit for the Altium MCP server.

Given (1) a flat component list (as returned by ``get_all_component_data``) and
(2) per-net pad membership (designator-pad references grouped by net, as returned
by ``get_net_continuity``), this groups the decoupling/bypass capacitors that sit
on each power/supply net.

Kept free of Altium / Windows dependencies so it can be unit-tested offline and
reused by the ``get_power_decoupling_audit`` MCP tool.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple


# Net-name fragments that strongly imply a power / supply rail. Matched
# case-insensitively as substrings, plus the explicit voltage-style patterns
# below (3V3, 1V8, +5V, 12V, VCC, VDD, ...).
_POWER_TOKENS = (
    "VCC", "VDD", "VBAT", "VBUS", "VIN", "VOUT", "VREF", "VSYS", "VDDA",
    "VDDIO", "VCCIO", "VPP", "VEE", "PWR", "POWER", "SUPPLY", "RAIL",
    "+5V", "+3V3", "+3V", "+1V8", "+12V", "+24V",
)

# Voltage rail like "3V3", "1V8", "5V0", "12V", "+5V", "-12V".
_VOLTAGE_RE = re.compile(r"^[+-]?\d+V\d*$", re.IGNORECASE)

# Ground nets are not decoupling targets; excluded from the supply-net set.
_GROUND_TOKENS = ("GND", "GROUND", "VSS", "AGND", "DGND", "PGND", "EARTH")


def _natural_key(ref: str) -> Tuple[str, int, str]:
    """Sort designators/refs like a human: C2 before C10."""
    m = re.match(r"^([A-Za-z_]*)(\d*)", ref or "")
    prefix = m.group(1) if m else (ref or "")
    num = int(m.group(2)) if (m and m.group(2)) else 0
    return (prefix, num, ref or "")


def is_ground_net(net_name: str) -> bool:
    name = (net_name or "").strip().upper()
    if not name:
        return False
    return any(tok in name for tok in _GROUND_TOKENS)


def is_power_net(net_name: str) -> bool:
    """Heuristic: does this net name look like a power/supply rail?

    Ground nets are deliberately excluded (they are returns, not rails).
    """
    name = (net_name or "").strip()
    if not name:
        return False
    if is_ground_net(net_name):
        return False
    upper = name.upper()
    if _VOLTAGE_RE.match(name):
        return True
    return any(tok in upper for tok in _POWER_TOKENS)


def is_capacitor(component: Dict[str, Any]) -> bool:
    """A component is treated as a capacitor if its designator starts with 'C'
    (but not 'CON'/'CN' style connectors) or its description mentions a cap."""
    designator = (component.get("designator") or component.get("name") or "").strip()
    description = (component.get("description") or "").lower()
    if "cap" in description:
        return True
    if designator:
        d = designator.upper()
        # Designator like C1, C12, C100 -> capacitor. Avoid connectors (CON1, CN1).
        m = re.match(r"^C(\d+)$", d)
        if m:
            return True
    return False


def _designator_of_ref(ref: str) -> str:
    """'C12-1' -> 'C12'. Splits on the last '-' so designators that contain a
    hyphen are not mangled (none normally do, but be safe)."""
    ref = (ref or "").strip()
    if not ref:
        return ""
    if "-" in ref:
        return ref.rsplit("-", 1)[0].strip()
    return ref


def audit_decoupling(
    components: List[Dict[str, Any]],
    net_pads: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Group decoupling capacitors by power/supply net.

    Parameters
    ----------
    components:
        Flat component list (``designator``/``description`` keys).
    net_pads:
        Mapping of net name -> list of pad refs in ``DESIGNATOR-PAD`` form
        (e.g. ``{"3V3": ["C1-1", "U2-8", "R3-2"]}``). Other shapes are tolerated:
        a list of plain designators also works.

    Returns
    -------
    dict with ``power_nets`` (audit per supply net, sorted by name) plus summary
    counters. Each power-net entry lists the connected capacitors (designators)
    and a ``capacitor_count``. Nets with zero decoupling caps are still reported
    so the user can spot un-bypassed rails.
    """
    # Build the set of designators that are capacitors.
    cap_designators = set()
    for comp in components or []:
        if is_capacitor(comp):
            desig = (comp.get("designator") or comp.get("name") or "").strip()
            if desig:
                cap_designators.add(desig)

    power_nets: List[Dict[str, Any]] = []
    total_caps_used = set()

    for net_name in sorted((net_pads or {}).keys(), key=lambda n: _natural_key(n)):
        if not is_power_net(net_name):
            continue

        refs: Iterable[str] = net_pads.get(net_name) or []
        caps_on_net = set()
        for ref in refs:
            desig = _designator_of_ref(ref)
            if desig in cap_designators:
                caps_on_net.add(desig)

        caps_sorted = sorted(caps_on_net, key=_natural_key)
        total_caps_used.update(caps_on_net)
        power_nets.append(
            {
                "net": net_name,
                "capacitor_count": len(caps_sorted),
                "capacitors": caps_sorted,
                "decoupled": len(caps_sorted) > 0,
            }
        )

    undecoupled = [p["net"] for p in power_nets if not p["decoupled"]]

    return {
        "total_power_nets": len(power_nets),
        "total_decoupling_caps": len(total_caps_used),
        "undecoupled_power_nets": undecoupled,
        "power_nets": power_nets,
    }
