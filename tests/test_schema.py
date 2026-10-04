"""The interchange schema is checked against fixtures; semantic checks live in core."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/case.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def test_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize('name', ['counterexample', 'no-finding', 'already-corrected', 'unverified-source', 'open-objection'])
def test_example_structures(name):
    VALIDATOR.validate(json.loads((ROOT / 'examples' / name / 'case.json').read_text()))


@pytest.mark.parametrize('field,value', [
    ('contact_authorized', True), ('reviews', []), ('origin', {}), ('confidence', 0),
])
def test_schema_rejects_invented_or_legacy_control_fields(bundle, field, value):
    root, case, data = bundle
    case[field] = value
    assert list(VALIDATOR.iter_errors(case))


def test_schema_rejects_numeric_floats_for_claim_bound(bundle):
    root, case, data = bundle
    case['claim']['formalization']['upper_bound'] = 0.5
    assert list(VALIDATOR.iter_errors(case))
