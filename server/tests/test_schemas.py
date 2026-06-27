"""
Tier A (no-Altium) contract tests.

Validates captured tool-output fixtures against JSON schemas, and locks in
regressions for bugs we've already fixed. Runs anywhere with just
`pip install pytest jsonschema` -- no Altium required -- so it can gate CI.
"""

import json
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "schemas"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

SUFFIX = ".schema.json"


def _schema_fixture_pairs():
    pairs = []
    for schema in sorted(SCHEMA_DIR.glob("*" + SUFFIX)):
        stem = schema.name[: -len(SUFFIX)]
        fixture = FIXTURE_DIR / f"{stem}.sample.json"
        if fixture.exists():
            pairs.append((schema, fixture))
    return pairs


@pytest.mark.parametrize(
    "schema_path,fixture_path",
    _schema_fixture_pairs(),
    ids=lambda p: p.name,
)
def test_fixture_matches_schema(schema_path, fixture_path):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)


def test_every_schema_has_a_fixture():
    missing = []
    for schema in SCHEMA_DIR.glob("*" + SUFFIX):
        stem = schema.name[: -len(SUFFIX)]
        if not (FIXTURE_DIR / f"{stem}.sample.json").exists():
            missing.append(schema.name)
    assert not missing, f"schemas without a fixture: {missing}"


def test_stackup_regression_core_present():
    """Regression guard for the core-dielectric bug.

    Before the fix, internal core dielectrics were dropped and a 4-layer board
    reported ~0.46 mm total. The core must be present and total thickness must
    include it.
    """
    data = json.loads(
        (FIXTURE_DIR / "pcb_layer_stackup.sample.json").read_text(encoding="utf-8")
    )
    diel_types = [layer.get("dielectric_type") for layer in data["layers"]]
    assert "Core" in diel_types, "core dielectric missing from stackup output"
    assert data["total_thickness_mm"] > 1.0, "total thickness looks like the core was dropped"
