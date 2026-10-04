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
    out = subprocess.run([sys.executable, '-m', 'researchwitness', 'capabilities'],
                         capture_output=True, text=True, check=True)
    kinds = {x['kind'] for x in json.loads(out.stdout)['checkers']}
    assert {'finite_field_polynomial_residue', 'finite_map_fixed_point'} <= kinds


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
