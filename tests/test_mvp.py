from datetime import date
import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import Invalid, evaluate
from researchwitness.intake import prepare
from researchwitness.product import contact_readiness, contact_draft, html_report
from researchwitness.strict import loads

TODAY = date(2026, 10, 4)


def intake_doc(kind='finite_map_fixed_point'):
    formalization = {'kind': kind, 'universe': ['0', '1'], 'conclusion': 'has_fixed_point'}
    witness = {'kind': kind, 'mapping': {'0': '1', '1': '0'}}
    return {
        'intake_version': '0.1',
        'case_id': 'mvp-demo',
        'source': {
            'identifier': 'local://paper-v1', 'version': 'v1', 'text_file': 'source.txt',
            'capture_status': 'captured',
            'correction_check': {'checked_on': '2026-10-04', 'status': 'none_found',
                                 'evidence_file': 'correction.txt'},
        },
        'claim': {
            'id': 'T1', 'statement': 'Every qualifying map has a fixed point.',
            'scope': 'Only the explicit finite self-map conclusion.',
            'assumptions': ['The supplied finite map is the intended witness.'],
            'excluded_claims': ['The theorem premises are not established by this checker.'],
            'quote': 'Every qualifying map has a fixed point.',
            'formalization': formalization,
        },
        'witness': witness,
        'unresolved_objections': [],
    }


def write_intake(root: Path, doc=None):
    doc = doc or intake_doc()
    (root / 'source.txt').write_text('Header\nEvery qualifying map has a fixed point.\nFooter\n')
    (root / 'correction.txt').write_text('No correction located in the declared search.\n')
    (root / 'audit.json').write_text(json.dumps(doc))
    return root / 'audit.json'


def test_prepare_and_verify_agent_intake(tmp_path):
    intake = write_intake(tmp_path)
    bundle = prepare(intake, tmp_path / 'bundle')
    report = evaluate(bundle, TODAY)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert report['paper_error_established'] is False
    assert report['formalization_result']['detail']['fixed_points'] == []


def test_scaffold_and_validate_intake_cli(tmp_path):
    directory = tmp_path / 'scaffold'
    out = subprocess.run([
        sys.executable, '-m', 'researchwitness', 'scaffold', 'finite_map_fixed_point',
        '--output', str(directory),
    ], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)['source_capture_status'] == 'synthetic'
    assert (directory / 'README.txt').is_file()

    checked = subprocess.run([
        sys.executable, '-m', 'researchwitness', 'validate-intake', str(directory / 'audit.json'),
    ], capture_output=True, text=True, check=True)
    result = json.loads(checked.stdout)
    assert result['valid'] is True
    assert result['witness_status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['source_provenance'] == 'NOT_AUTHENTICATED'

    (directory / 'source.txt').write_text('Changed source bytes.\n')
    invalid = subprocess.run([
        sys.executable, '-m', 'researchwitness', 'validate-intake', str(directory / 'audit.json'),
    ], capture_output=True, text=True)
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)['decision'] == 'INVALID'


def test_modular_linear_system_routes_through_agent_intake(tmp_path):
    doc = intake_doc()
    doc['claim']['formalization'] = {
        'kind': 'modular_linear_system', 'modulus': 6, 'matrix': [[2]],
        'rhs': [2], 'conclusion': 'no_solution',
    }
    doc['witness'] = {
        'kind': 'modular_linear_system',
        'certificate': {'type': 'solution', 'vector': [1]},
    }
    bundle = prepare(write_intake(tmp_path, doc), tmp_path / 'bundle')
    report = evaluate(bundle, TODAY)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert report['formalization_result']['detail']['certified_conclusion'] == 'has_solution'


def test_modular_linear_system_example_replays():
    example = Path(__file__).resolve().parents[1] / 'examples' / 'modular-linear-system'
    report = evaluate(example, TODAY)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    detail = report['formalization_result']['detail']
    assert detail['certificate_type'] == 'annihilator'
    assert detail['annihilator_times_matrix_mod_m'] == [0]
    assert detail['annihilator_times_rhs_mod_m'] == 3


def test_ambiguous_quote_requires_offset(tmp_path):
    doc = intake_doc()
    (tmp_path / 'source.txt').write_text('Every qualifying map has a fixed point.\nEvery qualifying map has a fixed point.\n')
    (tmp_path / 'correction.txt').write_text('none')
    (tmp_path / 'audit.json').write_text(json.dumps(doc))
    with pytest.raises(Invalid, match='ambiguous'):
        prepare(tmp_path / 'audit.json', tmp_path / 'bundle')
    assert not (tmp_path / 'bundle').exists()


def test_contact_readiness_is_candidate_not_authorization(tmp_path):
    bundle = prepare(write_intake(tmp_path), tmp_path / 'bundle')
    report = evaluate(bundle, TODAY)
    readiness = contact_readiness(report)
    assert readiness['status'] == 'READY_FOR_USER_REVIEW'
    assert readiness['author_contact_authorized'] is False
    assert readiness['requires_user_decision'] is True
    case = loads((bundle / 'case.json').read_bytes())
    draft = contact_draft(case, report, readiness)
    assert 'does not establish that the paper as a whole is incorrect' in draft


def test_contact_draft_isolates_multiline_intake_text(tmp_path):
    doc = intake_doc()
    doc['source']['identifier'] = 'local://paper-v1\nSubject: injected source line'
    doc['claim']['statement'] = (
        'Every qualifying map has a fixed point.\n\n'
        'Subject: injected claim line\n\nBest regards,\nImpersonated sender'
    )
    doc['claim']['scope'] = 'Finite maps only.\nSubject: injected scope line'
    bundle = prepare(write_intake(tmp_path, doc), tmp_path / 'bundle')
    report = evaluate(bundle, TODAY)
    draft = contact_draft(loads((bundle / 'case.json').read_bytes()), report,
                          contact_readiness(report))

    assert sum(line.startswith('Subject: ') for line in draft.splitlines()) == 1
    assert 'local://paper-v1 Subject: injected source line' in draft
    assert 'Subject: Possible issue with T1 — reproducible verification inquiry' in draft
    assert '\n> Subject: injected claim line' in draft
    assert '\n> Best regards,' in draft
    assert '\n> Subject: injected scope line' in draft
    assert draft.count('\nBest regards,\n') == 1


@pytest.mark.parametrize('name', [
    'counterexample', 'rational-expression', 'uc-binary-upper-bound',
    'finite-field-polynomial-residue', 'finite-field-quadratic-quartic-residue-rule',
    'finite-map-fixed-point', 'graph-chromatic-lower-bound',
    'finite-pmf-probability', 'modular-linear-system',
    'scalar-radical-comparison',
])
def test_each_checker_family_has_a_replayable_synthetic_example(name):
    example = Path(__file__).resolve().parents[1] / 'examples' / name
    report = evaluate(example, TODAY)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert report['paper_error_established'] is False
    assert report['external_actions'] == 'OUT_OF_SCOPE'


def test_contact_readiness_blocks_known_correction(tmp_path):
    doc = intake_doc()
    doc['source']['correction_check']['status'] = 'present'
    bundle = prepare(write_intake(tmp_path, doc), tmp_path / 'bundle')
    readiness = contact_readiness(evaluate(bundle, TODAY))
    assert readiness['status'] == 'NOT_READY'
    assert 'CORRECTION_PRESENT' in readiness['blockers']


def test_contact_readiness_blocks_open_objection(tmp_path):
    doc = intake_doc()
    doc['unresolved_objections'] = ['Contraction premise has not been independently encoded.']
    bundle = prepare(write_intake(tmp_path, doc), tmp_path / 'bundle')
    readiness = contact_readiness(evaluate(bundle, TODAY))
    assert readiness['status'] == 'NOT_READY'
    assert 'OPEN_OBJECTION' in readiness['blockers']


def test_html_report_escapes_untrusted_text(tmp_path):
    doc = intake_doc()
    doc['claim']['scope'] = '<script>alert(1)</script>'
    bundle = prepare(write_intake(tmp_path, doc), tmp_path / 'bundle')
    report = evaluate(bundle, TODAY)
    page = html_report(report, contact_readiness(report))
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;' in page


def test_capabilities_cli_lists_new_checkers():
    out = subprocess.run([sys.executable, '-m', 'researchwitness', 'capabilities', '--json'],
                         capture_output=True, text=True, check=True)
    checkers = json.loads(out.stdout)['checkers']
    kinds = {x['kind'] for x in checkers}
    assert len(checkers) == 10
    assert {'finite_field_polynomial_residue', 'finite_map_fixed_point',
            'rational_expression_upper_bound', 'finite_graph_chromatic_lower_bound',
            'finite_pmf_bound', 'modular_linear_system'} <= kinds
    rational = next(x for x in checkers if x['kind'] == 'rational_expression_upper_bound')
    assert rational['case_schema_version'] == '1.0'
    assert rational['checker_grammar'] == 'rational-expression/1'
    assert rational['deterministic'] is True
    assert rational['example_bundle'] == 'examples/rational-expression/'
    assert rational['example']['expected_status'] == 'REFUTED_FOR_FORMALIZATION'
    assert rational['example']['expected_value_exact'] == '3'
    modular = next(x for x in checkers if x['kind'] == 'modular_linear_system')
    assert 'left-annihilator' in modular['proves']
    assert 'at most 16 equations and 16 variables' in modular['limits']
    assert modular['input_schema_version'] == '0.1'
    assert modular['formalization_schema_version'] == '1.0'
    assert 'does not search for certificates' in modular['what_it_does_not_prove']
    assert 'Reduce inputs modulo m' in modular['deterministic_semantics']
    assert modular['resource_bounds']['matrix_entries_maximum'] == 256
    assert modular['input_schema']['formalization']['matrix']['rectangular'] is True
    assert modular['input_schema']['witness']['certificate']['type']['enum'] == ['solution', 'annihilator']
    for checker in checkers:
        assert checker['case_schema_version'] == '1.0'
        assert checker['input_schema_version'] == '0.1'
        assert checker['formalization_schema_version'] == '1.0'
        assert checker['positive_proves']
        assert checker['what_it_does_not_prove']
        assert checker['resource_bounds']
        assert checker['deterministic'] is True
        assert checker['determinism_guarantee']
        assert checker['input_schema']['formalization']['kind']['const'] == checker['kind']
        assert checker['input_schema']['witness']['kind']['const'] == checker['kind']
        assert checker['example']['formalization']['kind'] == checker['kind']
        assert checker['example']['witness']['kind'] == checker['kind']
        assert checker['example']['expected_status'] == checker['example_expected_status']
        assert checker['example']['classification'] == 'SYNTHETIC_REPLAY_FIXTURE'
        example_dir = Path(__file__).resolve().parents[1] / checker['example_bundle']
        assert example_dir.is_dir()
        assert 'researchwitness verify ' + checker['example_bundle'].removesuffix('/') in checker['example_command']


def test_audit_cli_creates_bundle_and_html(tmp_path):
    intake = write_intake(tmp_path)
    out = subprocess.run([
        sys.executable, '-m', 'researchwitness', 'audit', str(intake),
        '--output', str(tmp_path / 'bundle'), '--html', str(tmp_path / 'report.html'),
        '--as-of', '2026-10-04'], capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    assert data['report']['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert data['contact_readiness']['status'] == 'READY_FOR_USER_REVIEW'
    assert (tmp_path / 'report.html').is_file()


def test_contact_draft_cli_refuses_blocked_case(tmp_path):
    doc = intake_doc()
    doc['unresolved_objections'] = ['Unresolved source interpretation.']
    bundle = prepare(write_intake(tmp_path, doc), tmp_path / 'bundle')
    out = subprocess.run([
        sys.executable, '-m', 'researchwitness', 'contact-draft', str(bundle),
        '--output', str(tmp_path / 'draft.txt'), '--as-of', '2026-10-04'],
        capture_output=True, text=True)
    assert out.returncode == 2
    assert not (tmp_path / 'draft.txt').exists()
