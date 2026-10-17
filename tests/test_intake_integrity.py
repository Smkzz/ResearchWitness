"""Regressions for validation/preparation parity and generated export names."""
from datetime import date
import json

import pytest
from jsonschema import Draft202012Validator

from researchwitness import Invalid, evaluate
from researchwitness.__main__ import main
from researchwitness.intake import prepare, validate_intake_file
from researchwitness.scaffold import scaffold
from researchwitness.strict import byte_hash
from tools.write_schema import make_intake_schema


def _intake(tmp_path):
    root = scaffold('finite_map_fixed_point', tmp_path / 'intake')
    path = root / 'audit.json'
    return path, json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize('field,value', [
    (('case_id',), 'identifier with spaces'),
    (('claim', 'id'), 'claim/with/path'),
    (('claim', 'assumptions'), [42]),
    (('claim', 'assumptions'), ['duplicate', 'duplicate']),
    (('claim', 'assumptions'), [f'premise-{i}' for i in range(65)]),
    (('claim', 'excluded_claims'), ['duplicate', 'duplicate']),
    (('unresolved_objections',), ['duplicate', 'duplicate']),
    (('unresolved_objections',), [f'objection-{i}' for i in range(65)]),
    (('claim', 'formalization', 'kind'), []),
    (('claim', 'formalization', 'kind'), {}),
])
def test_intake_schema_validation_and_preparation_reject_invalid_metadata(tmp_path, field, value):
    path, doc = _intake(tmp_path)
    target = doc
    for part in field[:-1]:
        target = target[part]
    target[field[-1]] = value
    path.write_text(json.dumps(doc), encoding='utf-8')

    assert not Draft202012Validator(make_intake_schema()).is_valid(doc)
    with pytest.raises(Invalid):
        validate_intake_file(path)
    with pytest.raises(Invalid):
        prepare(path, tmp_path / 'bundle')
    assert not (tmp_path / 'bundle').exists()


def test_valid_intake_still_prepares_and_replays(tmp_path):
    path, doc = _intake(tmp_path)
    doc['case_id'] = 'case_1.v2-alpha'
    doc['claim']['assumptions'] = [f'premise-{i}' for i in range(64)]
    doc['unresolved_objections'] = [f'objection-{i}' for i in range(64)]
    path.write_text(json.dumps(doc), encoding='utf-8')

    assert validate_intake_file(path)['valid'] is True
    bundle = prepare(path, tmp_path / 'bundle')
    assert evaluate(bundle, date(2026, 10, 4))['paper_error_established'] is False


def test_intake_artifacts_share_the_bundle_total_size_limit(tmp_path, monkeypatch):
    from researchwitness import intake

    path, doc = _intake(tmp_path)
    doc['notes_files'] = ['note.txt']
    (path.parent / 'note.txt').write_bytes(b'x' * 512)
    path.write_text(json.dumps(doc), encoding='utf-8')
    # Exercise the production cumulative bound without allocating a 64 MiB fixture.
    monkeypatch.setattr(intake, 'MAX_BUNDLE_BYTES', 512, raising=False)
    with pytest.raises(Invalid, match='Total bundle size limit'):
        validate_intake_file(path)
    with pytest.raises(Invalid, match='Total bundle size limit'):
        prepare(path, tmp_path / 'bundle')
    assert not (tmp_path / 'bundle').exists()


@pytest.mark.parametrize('name', [
    'contact-readiness.json', 'CONTACT-READINESS.JSON',
    'report.json/attachment.txt', 'Report.JSON/attachment.txt',
    'contact-readiness.json/attachment.txt',
])
def test_pack_rejects_artifacts_that_collide_with_generated_entries(tmp_path, bundle, name):
    root, case, _ = bundle
    content = b'operator-supplied attachment\n'
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    case['artifacts'][name] = byte_hash(content)
    (root / 'case.json').write_text(json.dumps(case), encoding='utf-8')

    archive = tmp_path / 'evidence.zip'
    assert main(['pack', str(root), '--as-of', '2026-10-04', '--output', str(archive)]) == 2
    assert not archive.exists()
