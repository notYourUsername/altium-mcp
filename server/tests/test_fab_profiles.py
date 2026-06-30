"""
Tier A (no-Altium) tests for fab-house profiles.

Every profile under /fab_profiles must validate against the profile schema, and
any profile still marked verified=false must not be silently treated as
manufacturing-ready.
"""

import json
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[2]
FP_DIR = REPO / "server" / "fab_profiles"
SCHEMA_PATH = FP_DIR / "fab_profile.schema.json"


def _profiles():
    return [p for p in FP_DIR.glob("*.json") if p.name != SCHEMA_PATH.name]


def test_profiles_exist():
    assert _profiles(), "no fab profiles found in /fab_profiles"


def test_profiles_match_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for profile in _profiles():
        data = json.loads(profile.read_text(encoding="utf-8"))
        jsonschema.validate(instance=data, schema=schema)


def test_template_is_marked_unverified():
    """The shipped template must never claim to be verified fab data."""
    template = FP_DIR / "_TEMPLATE.json"
    data = json.loads(template.read_text(encoding="utf-8"))
    assert data["verified"] is False
