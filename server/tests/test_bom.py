"""
Tier A (no-Altium) tests for BOM aggregation.

Exercises build_bom() against a component list captured live from the
GPS-Teseo4 board, plus a small synthetic case for grouping/sorting.
"""

import json
import sys
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))

from bom import build_bom  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA = REPO / "schemas" / "bom.schema.json"


def _components():
    # PowerShell wrote this fixture as UTF-8 with BOM; utf-8-sig strips it.
    return json.loads((FIXTURES / "component_data.sample.json").read_text(encoding="utf-8-sig"))


def test_build_bom_matches_schema():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(instance=build_bom(_components()), schema=schema)


def test_build_bom_conserves_count_and_aggregates():
    comps = _components()
    result = build_bom(comps)
    # Every component appears exactly once across all BOM lines
    assert result["total_components"] == len(comps)
    # Grouping actually reduced the number of lines
    assert result["total_lines"] < len(comps)
    for line in result["bom"]:
        assert line["quantity"] == len(line["designators"])
        assert line["designators"] == sorted(set(line["designators"]), key=line["designators"].index)


def test_build_bom_groups_identical_parts_and_natural_sorts():
    comps = [
        {"designator": "R10", "description": "10k 0402", "footprint": "R0402"},
        {"designator": "R2", "description": "10k 0402", "footprint": "R0402"},
        {"designator": "C1", "description": "100nF", "footprint": "C0402"},
    ]
    result = build_bom(comps)
    assert result["total_lines"] == 2
    res_line = [l for l in result["bom"] if l["footprint"] == "R0402"][0]
    assert res_line["quantity"] == 2
    assert res_line["designators"] == ["R2", "R10"]  # natural sort, not lexical
