"""
Pure-Python BOM aggregation for the Altium MCP server.

Groups the flat component list returned by the `get_all_component_data` command
into Bill-of-Materials lines (one per unique part), with quantity and the list of
designators. Intentionally free of Altium / Windows dependencies so it can be
unit-tested offline and reused by the `get_bom` MCP tool.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _natural_key(designator: str) -> Tuple[str, int, str]:
    """Sort designators like a human: R2 before R10."""
    m = re.match(r"^([A-Za-z_]*)(\d*)", designator or "")
    prefix = m.group(1) if m else (designator or "")
    num = int(m.group(2)) if (m and m.group(2)) else 0
    return (prefix, num, designator or "")


def build_bom(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a flat component list into BOM lines keyed by (description, footprint)."""
    groups: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for comp in components or []:
        description = (comp.get("description") or "").strip()
        footprint = (comp.get("footprint") or "").strip()
        designator = (comp.get("designator") or comp.get("name") or "").strip()

        key = (description, footprint)
        line = groups.get(key)
        if line is None:
            line = {"description": description, "footprint": footprint, "designators": []}
            groups[key] = line
        if designator:
            line["designators"].append(designator)

    bom: List[Dict[str, Any]] = []
    for line in groups.values():
        line["designators"] = sorted(set(line["designators"]), key=_natural_key)
        line["quantity"] = len(line["designators"])
        bom.append(line)

    # Highest quantity first, then stable by description / footprint
    bom.sort(key=lambda r: (-r["quantity"], r["description"], r["footprint"]))

    return {
        "total_components": sum(r["quantity"] for r in bom),
        "total_lines": len(bom),
        "bom": bom,
    }
