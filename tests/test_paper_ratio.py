"""Adversarial tests for same-cell JATS n/N (%) arithmetic."""
from __future__ import annotations

from dataclasses import replace

import pytest

from researchwitness.jats import parse_jats
from researchwitness.paper_ratio import check_jats_cell_ratio_percentages


def _document(
    value: str,
    *,
    row_label: str = 'Transferred',
    caption: str = 'Disposition',
    footnote: str | None = None,
    reference: bool = False,
):
    xref = '<xref ref-type="table-fn" rid="fn1">a</xref>' if reference else ''
    footnote_xml = (
        f'<table-wrap-foot><fn id="fn1"><label>a</label><p>{footnote}</p></fn></table-wrap-foot>'
        if footnote is not None else ''
    )
    source = (
        '<article><body><table-wrap id="T1"><label>Table 1</label>'
        f'<caption><title>{caption}</title></caption><table><thead><tr>'
        '<th>Outcome</th><th>n/N (%)</th></tr></thead><tbody><tr>'
        f'<th scope="row">{row_label}</th><td>{value}{xref}</td>'
        f'</tr></tbody></table>{footnote_xml}</table-wrap></body></article>'
    ).encode('utf-8')
    return parse_jats(source, 'paper.xml')


def test_mismatch_candidate_anchors_the_exact_cell_and_binds_source_hash():
    document = _document('11/233 (1.8%)')
    result = check_jats_cell_ratio_percentages(document)

    assert result['detector_id'] == 'jats_cell_ratio_percentage_recomputation'
    assert result['checked_cells'] == 1
    assert result['tables'][0]['status'] == 'ELIGIBLE'
    assert result['tables'][0]['candidate_count'] == 1
    assert result['relations'][0]['status'] == 'ELIGIBLE_CHECKED_MISMATCH'
    assert result['relations'][0]['finding_emitted'] is True
    candidate = result['findings'][0]
    assert candidate['status'] == 'CANDIDATE_ANOMALY'
    assert candidate['numerator_exact'] == '11'
    assert candidate['denominator_exact'] == '233'
    assert candidate['reported_percent'] == '1.8'
    assert candidate['recomputed_at_display_precision'] == '4.7'
    anchor = candidate['source_anchors'][0]
    assert anchor['source_sha256'] == document.source_sha256
    assert anchor['source_format'] == 'jats_xml'
    assert anchor['quote'] == '11/233 (1.8%)'
    assert '/table-wrap[1]/table[1]/tbody[1]/tr[1]/td[1]' in anchor['element_path']


@pytest.mark.parametrize(('value', 'rounded'), [
    ('15/200 (7.50%)', '7.50'),
    ('1/8 (12.5%)', '12.5'),
    ('1/6 (17%)', '17'),
])
def test_consistent_ratio_uses_display_precision(value, rounded):
    result = check_jats_cell_ratio_percentages(_document(value))

    assert result['findings'] == []
    assert result['checked_cells'] == 1
    assert result['tables'][0]['status'] == 'ELIGIBLE'


@pytest.mark.parametrize(('value', 'status', 'rounded'), [
    ('1/32 (3.13%)', 'ELIGIBLE_CHECKED_MATCH', '3.13'),
    ('1/32 (3.12%)', 'ELIGIBLE_CHECKED_MISMATCH', '3.13'),
])
def test_direct_ratio_uses_half_up_at_exact_rounding_boundary(value, status, rounded):
    result = check_jats_cell_ratio_percentages(_document(value))

    assert result['relations'][0]['status'] == status
    assert result['relations'][0]['recomputed_at_display_precision'] == rounded


@pytest.mark.parametrize('value', [
    '1/0 (10%)',
    '2/1 (100%)',
    '1/2 (100.1%)',
])
def test_unsupported_numeric_domains_fail_closed(value):
    result = check_jats_cell_ratio_percentages(_document(value))

    assert result['findings'] == []
    assert result['checked_cells'] == 0
    assert result['tables'][0]['status'] == 'UNSUPPORTED'
    assert result['tables'][0]['skip_reasons']
    assert result['relations'][0]['status'] == 'UNSUPPORTED'
    assert result['relation_telemetry']['accounting_invariant'] is True


def test_known_display_and_glossary_note_is_safe_for_direct_cell_arithmetic():
    note = (
        'The variables are shown as n (%) ACC aortic cross clamping, ED emergency department, '
        'ICU intensive care unit, REBOA resuscitative endovascular balloon occlusion of the aorta '
        '*Chi-square test'
    )
    result = check_jats_cell_ratio_percentages(_document('11/233 (1.8%)', footnote=note))

    assert result['checked_cells'] == 1
    assert result['tables'][0]['status'] == 'ELIGIBLE'
    assert result['tables'][0]['skip_reasons'] == []


@pytest.mark.parametrize(('footnote', 'expected_reason'), [
    ('Multiple responses permitted.', 'FOOTNOTE_SCOPE_UNRESOLVED'),
    ('Percentages use available cases.', 'FOOTNOTE_SCOPE_UNRESOLVED'),
    ('The denominator varies by row.', 'FOOTNOTE_SCOPE_UNRESOLVED'),
    ('See the online supplement.', 'FOOTNOTE_SCOPE_UNRESOLVED'),
])
def test_scope_or_unrecognized_footnote_blocks_candidate(footnote, expected_reason):
    result = check_jats_cell_ratio_percentages(_document('11/233 (1.8%)', footnote=footnote))

    assert result['findings'] == []
    assert result['checked_cells'] == 0
    assert expected_reason in result['tables'][0]['skip_reasons']


@pytest.mark.parametrize(('caption', 'row_label', 'expected_reason'), [
    ('Weighted discharge percentages', 'Transferred', 'WEIGHTED_RESULT'),
    ('Disposition', 'Transferred due to missing data', 'MISSINGNESS_CHANGES_DENOMINATOR'),
    ('Disposition', 'Transferred (denominator varies)', 'MISSINGNESS_CHANGES_DENOMINATOR'),
])
def test_local_unsafe_table_or_row_semantics_are_skipped(caption, row_label, expected_reason):
    result = check_jats_cell_ratio_percentages(
        _document('11/233 (1.8%)', caption=caption, row_label=row_label),
    )

    assert result['findings'] == []
    assert result['tables'][0]['status'] == ('UNSUPPORTED' if expected_reason == 'WEIGHTED_RESULT' else 'INCOMPLETE')
    assert expected_reason in result['relations'][0]['secondary_skip_reasons'] + [
        result['relations'][0]['primary_skip_reason'],
    ]


def test_footnoted_cell_is_skipped_even_if_note_looks_like_display_metadata():
    result = check_jats_cell_ratio_percentages(_document(
        '11/233 (1.8%)', footnote='The variables are shown as n (%)', reference=True,
    ))

    assert result['findings'] == []
    assert result['checked_cells'] == 0
    assert 'FOOTNOTE_SCOPE_UNRESOLVED' in result['relations'][0]['secondary_skip_reasons'] + [
        result['relations'][0]['primary_skip_reason'],
    ]


def test_single_cell_check_does_not_depend_on_table_grid_but_preserves_parser_status():
    document = _document('11/233 (1.8%)')
    table = document.tables[0]
    document = replace(document, tables=(replace(table, structure_status='TABLE_STRUCTURE_UNSUPPORTED'),))

    result = check_jats_cell_ratio_percentages(document)

    assert result['tables'][0]['parser_status'] == 'TABLE_STRUCTURE_UNSUPPORTED'
    assert result['tables'][0]['status'] == 'ELIGIBLE'
    assert result['checked_cells'] == 1


@pytest.mark.parametrize(('value', 'reason'), [
    ('1,000/10,000 (10%)', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'),
    ('10/20 (50,0%)', 'DECIMAL_SEPARATOR_UNSUPPORTED'),
    ('10.5/20 (52.5%)', 'MALFORMED_NUMERIC_TOKEN'),
])
def test_unrecognized_direct_numeric_formats_are_counted_as_skipped_relations(value, reason):
    result = check_jats_cell_ratio_percentages(_document(value))

    assert result['potential_cells'] == 1
    assert result['checked_cells'] == 0
    assert result['skipped_cells'] == 1
    relation = result['relations'][0]
    assert relation['status'] == 'UNSUPPORTED'
    assert reason in relation['secondary_skip_reasons'] + [relation['primary_skip_reason']]
    assert result['relation_telemetry']['primary_skip_reason_counts'] == {relation['primary_skip_reason']: 1}
    assert result['relation_telemetry']['accounting_invariant'] is True


def test_explicit_same_cell_ratio_remains_eligible_under_overlapping_thresholds():
    document = _document('23/30 (76.7%)', row_label='At least 75%', caption='Cumulative outcomes')

    result = check_jats_cell_ratio_percentages(document)

    assert result['checked_cells'] == 1
    assert result['relations'][0]['status'] == 'ELIGIBLE_CHECKED_MATCH'
    assert result['findings'] == []


def test_direct_ratio_without_a_source_row_identity_is_incomplete():
    result = check_jats_cell_ratio_percentages(_document('11/233 (1.8%)', row_label=''))

    assert result['checked_cells'] == 0
    assert result['relations'][0]['status'] == 'INCOMPLETE'
    assert result['relations'][0]['primary_skip_reason'] == 'SOURCE_SCOPE_AMBIGUOUS'
