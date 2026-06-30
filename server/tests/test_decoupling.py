"""
Tier A (no-Altium) tests for the power-decoupling audit.

Exercises audit_decoupling() and its net/capacitor classifiers entirely with
synthetic data - no Altium dependency.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))

from decoupling import (  # noqa: E402
    audit_decoupling,
    is_capacitor,
    is_power_net,
    is_ground_net,
)


def test_is_power_net_classifies_rails():
    for name in ("3V3", "1V8", "+5V", "12V", "VCC", "VDD33", "VBUS", "VsysPWR"):
        assert is_power_net(name), name


def test_is_power_net_rejects_ground_and_signals():
    for name in ("GND", "AGND", "VSS", "PGND", "USB_D+", "SPI_CLK", "RESET", ""):
        assert not is_power_net(name), name


def test_is_ground_net():
    assert is_ground_net("GND")
    assert is_ground_net("DGND")
    assert not is_ground_net("3V3")


def test_is_capacitor_by_designator_and_description():
    assert is_capacitor({"designator": "C1"})
    assert is_capacitor({"designator": "C100"})
    assert is_capacitor({"designator": "U1", "description": "10uF X5R cap 0402"})
    # Connectors / ICs are not caps
    assert not is_capacitor({"designator": "CON1"})
    assert not is_capacitor({"designator": "U3", "description": "MCU"})
    assert not is_capacitor({"designator": "R1"})


def _components():
    return [
        {"designator": "C1", "description": "100nF 0402"},
        {"designator": "C2", "description": "10uF 0805"},
        {"designator": "C3", "description": "100nF 0402"},
        {"designator": "U1", "description": "GPS module"},
        {"designator": "R1", "description": "10k 0402"},
        {"designator": "CON1", "description": "USB connector"},
    ]


def _net_pads():
    return {
        "3V3": ["C1-1", "C2-1", "U1-8", "R1-1"],
        "GND": ["C1-2", "C2-2", "U1-4"],          # ground -> excluded
        "VBAT": ["C3-1", "U1-20"],
        "VCC_UNBYPASSED": ["U1-1"],               # power net with no cap
        "USB_D+": ["CON1-2", "U1-15"],            # signal -> excluded
    }


def test_audit_groups_caps_by_power_net():
    result = audit_decoupling(_components(), _net_pads())

    nets = {p["net"]: p for p in result["power_nets"]}
    # Ground and signal nets are not power nets
    assert "GND" not in nets
    assert "USB_D+" not in nets

    assert nets["3V3"]["capacitors"] == ["C1", "C2"]
    assert nets["3V3"]["capacitor_count"] == 2
    assert nets["3V3"]["decoupled"] is True

    assert nets["VBAT"]["capacitors"] == ["C3"]

    # Power net with no caps is reported as undecoupled
    assert nets["VCC_UNBYPASSED"]["capacitor_count"] == 0
    assert nets["VCC_UNBYPASSED"]["decoupled"] is False
    assert "VCC_UNBYPASSED" in result["undecoupled_power_nets"]


def test_audit_summary_counts():
    result = audit_decoupling(_components(), _net_pads())
    assert result["total_power_nets"] == 3      # 3V3, VBAT, VCC_UNBYPASSED
    # Unique caps used across power nets: C1, C2, C3
    assert result["total_decoupling_caps"] == 3
    # Power nets sorted naturally by name
    names = [p["net"] for p in result["power_nets"]]
    assert names == sorted(names, key=lambda n: n)


def test_audit_natural_sorts_capacitors():
    comps = [{"designator": f"C{n}"} for n in (1, 2, 10, 20)]
    net_pads = {"3V3": ["C10-1", "C2-1", "C1-1", "C20-1"]}
    result = audit_decoupling(comps, net_pads)
    assert result["power_nets"][0]["capacitors"] == ["C1", "C2", "C10", "C20"]


def test_audit_tolerates_plain_designators():
    # net_pads values that are plain designators (no -PAD suffix) still work
    comps = [{"designator": "C5"}]
    result = audit_decoupling(comps, {"5V0": ["C5", "U1"]})
    assert result["power_nets"][0]["capacitors"] == ["C5"]


def test_audit_empty_inputs():
    result = audit_decoupling([], {})
    assert result["total_power_nets"] == 0
    assert result["power_nets"] == []
