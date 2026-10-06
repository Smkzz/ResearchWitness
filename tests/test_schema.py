"""The interchange schema is checked against fixtures; semantic checks live in core."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/case.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
INTAKE_SCHEMA = json.loads((ROOT / 'schemas/intake.schema.json').read_text())
INTAKE_VALIDATOR = Draft202012Validator(INTAKE_SCHEMA, format_checker=FormatChecker())
REVIEW_SCHEMA = json.loads((ROOT / 'schemas/review.schema.json').read_text())
SUMMARY_SCHEMA = json.loads((ROOT / 'schemas/summary-check.schema.json').read_text())
PAPER_AUDIT_SCHEMA = json.loads((ROOT / 'schemas/paper-audit.schema.json').read_text())


def test_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator.check_schema(INTAKE_SCHEMA)
    Draft202012Validator.check_schema(REVIEW_SCHEMA)
    Draft202012Validator.check_schema(SUMMARY_SCHEMA)
    Draft202012Validator.check_schema(PAPER_AUDIT_SCHEMA)


@pytest.mark.parametrize('name', [
    'counterexample', 'no-finding', 'already-corrected', 'unverified-source', 'open-objection',
    'graph-chromatic-lower-bound', 'finite-pmf-probability', 'rational-expression', 'modular-linear-system',
    'scalar-radical-comparison', 'uc-binary-upper-bound', 'finite-field-polynomial-residue',
    'finite-field-quadratic-quartic-residue-rule', 'finite-map-fixed-point',
])
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


def test_schema_accepts_finite_pmf_expectation(bundle):
    root, case, data = bundle
    case['claim']['formalization'] = {
        'kind': 'finite_pmf_bound',
        'operation': 'expectation',
        'domains': {'x': ['low', 'high']},
        'payoffs': [
            {'assignment': {'x': 'low'}, 'value': '-1/2'},
            {'assignment': {'x': 'high'}, 'value': '3/2'},
        ],
        'relation': 'at_least',
        'bound': '0',
    }
    assert not list(VALIDATOR.iter_errors(case))


def test_schema_accepts_bounded_rational_expression_shape(bundle):
    root, case, data = bundle
    case['claim']['formalization'] = {
        'kind': 'rational_expression_upper_bound',
        'domain': {'x': {'lower': '1', 'upper': '3', 'lower_closed': False, 'upper_closed': True}},
        'expression': {
            'op': 'div',
            'left': {'op': 'pow', 'base': {'op': 'var', 'name': 'x'}, 'exponent': 2},
            'right': {'op': 'const', 'value': '2'},
        },
        'upper_bound': '2',
    }
    assert VALIDATOR.is_valid(case)
    case['claim']['formalization']['expression'] = {'op': 'eval', 'source': 'x + 1'}
    assert list(VALIDATOR.iter_errors(case))


def test_agent_intake_schema_accepts_all_checker_families_and_rejects_kind_mismatch():
    from researchwitness.checkers import capabilities

    for capability in capabilities():
        example = capability['example']
        intake = {
            'intake_version': '0.1',
            'case_id': 'schema-fixture',
            'source': {
                'identifier': 'synthetic:schema-fixture', 'version': 'v1',
                'text_file': 'source.txt', 'capture_status': 'synthetic',
                'correction_check': {
                    'checked_on': '2026-10-04', 'status': 'unchecked',
                    'evidence_file': 'correction.txt',
                },
            },
            'claim': {
                'id': 'C1', 'statement': example['statement'], 'scope': example['scope'],
                'assumptions': example['assumptions'],
                'excluded_claims': example['excluded_claims'],
                'quote': example['statement'], 'formalization': example['formalization'],
            },
            'witness': example['witness'],
            'unresolved_objections': [],
        }
        INTAKE_VALIDATOR.validate(intake)
        mismatched = json.loads(json.dumps(intake))
        mismatched['witness']['kind'] = 'scalar_radical_comparison' if capability['kind'] != 'scalar_radical_comparison' else 'polynomial_upper_bound'
        assert list(INTAKE_VALIDATOR.iter_errors(mismatched))


def test_schema_accepts_bounded_modular_linear_system(bundle):
    root, case, data = bundle
    case['claim']['formalization'] = {
        'kind': 'modular_linear_system', 'modulus': 6, 'matrix': [[2]],
        'rhs': [1], 'conclusion': 'no_solution',
    }
    assert not list(VALIDATOR.iter_errors(case))

    case['claim']['formalization']['modulus'] = 1
    assert list(VALIDATOR.iter_errors(case))
