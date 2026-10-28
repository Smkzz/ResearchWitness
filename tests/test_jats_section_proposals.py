"""Public synthetic controls for conditional multi-section JATS denominators."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from researchwitness.jats_section_proposals import main, review_section_denominators
from researchwitness._jats_parser import JATSSourceError


def _xml(*, first_section: bool = True, second_section: bool = True, second_label: str = "DVT and PE patients",
         second_value: str = "N = 71", row_label: str = "Unchanged, n (%)",
         caption: str = "Results", footer: str = "", span: str = "1") -> bytes:
    first = '<tr><td>DVT patients</td><td>N = 20</td><td>N = 43</td></tr>' if first_section else ''
    second = (f'<tr><td>{second_label}</td><td>N = 51</td><td>{second_value}</td></tr>'
              if second_section else "")
    return f'''<article><body><table-wrap id="T3"><caption><p>{caption}</p></caption>
<table><thead><tr><th>Outcome</th><th>Group</th><th>Combined</th></tr>
<tr><th>Patients</th><th>N = 20</th><th>N = 43</th></tr></thead><tbody>
{first}
<tr><td>Unchanged, n (%)</td><td>1 (5.0)</td><td>2 (4.7)</td></tr>
{second}
<tr><td>{row_label}</td><td>2 (3.9)</td><td colspan="{span}">2 (2.9)</td></tr>
<tr><td>Deteriorated, n (%)</td><td>0 (0.0)</td><td>1 (1.4)</td></tr>
</tbody></table><table-wrap-foot><fn><p>{footer}</p></fn></table-wrap-foot>
</table-wrap></body></article>'''.encode()


def test_local_section_produces_single_conditional_mismatch_and_evidence():
    source = _xml()
    r = review_section_denominators(source)
    assert (r['section_headers_seen'], r['conditional_pairs'],
            r['conditional_mismatch_count']) == (2, 6, 1)
    mismatch = next(x for x in r['proposals'] if
                    x['arithmetic_status_if_section_n_applies'] == 'conditional_mismatch')
    assert (mismatch['numerator'], mismatch['proposed_denominator'],
            mismatch['reported_percent'], mismatch['expected_at_printed_precision']) == (2, 71, '2.9', '2.8')
    assert mismatch['column_header_denominators'] == [43]
    assert mismatch['conflicting_header'] is True
    assert mismatch['scope_adjudicated'] is False
    assert mismatch['scientific_error_established'] is False
    for key, role, quote in [
        ('cell', 'source_cell', b'2 (2.9)'),
        ('section_denominator', 'same_column_section_n', b'N = 71'),
        ('row_label', 'explicit_row_n_percent', b'Unchanged, n (%)'),
    ]:
        ev = mismatch['source_evidence'][key]
        assert ev['role'] == role
        assert quote in source[ev['byte_start']:ev['byte_end']]
    assert r['source_sha256'] == hashlib.sha256(source).hexdigest()
    assert r['representation_authenticated'] is False
    assert r['changes_to_existing_audit'] is False
    assert r == review_section_denominators(source)


def test_zero_unverified_inference_without_source_section_or_row_cue():
    assert review_section_denominators(_xml(first_section=False, second_section=False))['conditional_mismatch_count'] == 0
    assert review_section_denominators(_xml(second_label='Other measures'))['conditional_mismatch_count'] == 0
    assert review_section_denominators(_xml(row_label='Unchanged'))['conditional_mismatch_count'] == 0
    assert review_section_denominators(_xml(second_value='N unknown'))['conditional_mismatch_count'] == 0


def test_malformed_section_clears_previous_section():
    r = review_section_denominators(_xml(second_value='N unknown'))
    # The preceding first group is valid; no stale denominator is applied to
    # any row following the malformed group boundary.
    assert r['conditional_pairs'] == 2
    assert r['conditional_mismatch_count'] == 0


@pytest.mark.parametrize('kwargs', [
    {'span': '2'},
    {'footer': 'All percentages were adjusted by age.'},
    {'caption': 'Figures rounded to nearest whole percent.'},
])
def test_unsupported_layout_or_methods_produce_no_unjustified_mismatch(kwargs):
    r = review_section_denominators(_xml(**kwargs))
    assert r['conditional_mismatch_count'] == 0


def test_existing_wheel_percentage_audit_not_mutated():
    from researchwitness._jats_parser import audit_jats_percentage_tables
    source = _xml()
    before = audit_jats_percentage_tables(source)
    review_section_denominators(source)
    after = audit_jats_percentage_tables(source)
    assert before == after


def test_unsupported_source_decl_rejected():
    source = _xml()
    with pytest.raises(JATSSourceError):
        review_section_denominators(b'<!DOCTYPE foo>' + source)


def test_cli_pins_source_and_does_not_create_files(tmp_path: Path, capsys):
    path = tmp_path/'fixture.xml'
    source = _xml()
    path.write_bytes(source)
    orig = sorted(p.name for p in tmp_path.iterdir())
    assert main([str(path), '--expected-source-sha256', '0'*64]) == 2
    assert capsys.readouterr().out == ''
    assert main([str(path), '--expected-source-sha256', hashlib.sha256(source).hexdigest()]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r['conditional_mismatch_count'] == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == orig


def test_file_symlink_not_admitted(tmp_path: Path, capsys):
    target = tmp_path / 'source.xml'
    source = _xml()
    target.write_bytes(source)
    link = tmp_path / 'link.xml'
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip('symlinks not available on this platform')
    assert main([str(link), '--expected-source-sha256', hashlib.sha256(source).hexdigest()]) == 2
    assert capsys.readouterr().out == ''
