"""Adversarial tests for source-mapped JATS SD/SE/n arithmetic."""
from __future__ import annotations

import pytest

from researchwitness.jats import parse_jats
from researchwitness.paper_statistics_source import check_jats_sd_se_n_tables


def _document(
    *,
    headers: tuple[str, ...] = ('n', 'SD', 'SE'),
    values: tuple[str, ...] = ('4', '6', '3'),
    title: str = 'Descriptive statistics',
    grouped_headers: tuple[str, ...] | None = None,
    row_label: str = 'Score',
    extra: str = '',
):
    assert len(headers) == len(values)
    header_rows = ''
    if grouped_headers is not None:
        assert len(grouped_headers) == len(headers)
        first = ''.join(f'<th>{item}</th>' for item in grouped_headers)
        second = ''.join(f'<th>{item}</th>' for item in headers)
        header_rows = f'<tr><th>Measure</th>{first}</tr><tr><th></th>{second}</tr>'
    else:
        header_rows = '<tr><th>Measure</th>' + ''.join(f'<th>{item}</th>' for item in headers) + '</tr>'
    source_cells = ''.join(f'<td>{value}</td>' for value in values)
    source = (
        '<article><front><article-meta><title-group><article-title>SD SE example</article-title>'
        '</title-group></article-meta></front><body><sec><title>Results</title>'
        f'<table-wrap id="T1"><label>Table 1</label><caption><title>{title}</title></caption>'
        f'<table><thead>{header_rows}</thead><tbody><tr><th scope="row">{row_label}</th>'
        f'{source_cells}</tr></tbody></table>{extra}</table-wrap>'
        '</sec></body></article>'
    ).encode('utf-8')
    return parse_jats(source, 'paper.xml')


def _table_result(document):
    return check_jats_sd_se_n_tables(document)['tables'][0]


def test_valid_row_returns_consistent_source_mapped_check_for_all_three_operands():
    document = _document(values=('4', '6', '3'))
    report = check_jats_sd_se_n_tables(document)

    table = report['tables'][0]
    assert table['applicability'] == 'APPLICABLE'
    assert table['eligibility'] == 'ELIGIBLE'
    assert table['checked_rows'] == 1
    assert table['candidate_count'] == 0
    assert table['skip_reasons'] == []
    check = table['checks'][0]
    assert check['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert check['recomputed_se_at_display_precision'] == '3'
    assert [(item['role'], item['source_anchor']['quote']) for item in check['source_anchors']] == [
        ('n', '4'), ('sd', '6'), ('se', '3'),
    ]
    assert all(item['source_anchor']['source_sha256'] == document.source_sha256
               for item in check['source_anchors'])
    assert all(item['source_anchor']['source_file'] == 'paper.xml'
               for item in check['source_anchors'])
    assert report['findings'] == []


def test_mismatch_is_candidate_and_preserves_three_operand_anchors():
    report = check_jats_sd_se_n_tables(_document(values=('4', '6', '2.9')))

    assert len(report['findings']) == 1
    candidate = report['findings'][0]
    assert candidate['status'] == 'ARITHMETIC_CANDIDATE'
    assert candidate['type'] == 'JATS_SD_SE_N_ARITHMETIC_MISMATCH'
    assert candidate['recomputed_se_at_display_precision'] == '3.0'
    assert candidate['n_exact'] == '4'
    assert candidate['sd_exact'] == '6'
    assert candidate['reported_se'] == '2.9'
    assert {item['role'] for item in candidate['source_anchors']} == {'n', 'sd', 'se'}
    assert len({item['source_anchor']['element_path'] for item in candidate['source_anchors']}) == 3


def test_reported_precision_controls_se_rounding():
    report = check_jats_sd_se_n_tables(_document(values=('3', '1', '0.58')))
    check = report['tables'][0]['checks'][0]
    assert check['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert check['recomputed_se_at_display_precision'] == '0.58'
    assert check['display_precision'] == 2


def test_sem_is_not_silently_treated_as_se_or_as_an_sd_label():
    table = _table_result(_document(headers=('n', 'SD', 'SEM'), values=('4', '6', '3')))

    assert table['applicability'] == 'APPLICABLE'
    assert table['eligibility'] == 'INCOMPLETE'
    assert table['checked_rows'] == 0
    assert table['candidate_count'] == 0
    assert table['skip_reasons'] == [{
        'reason': 'SEM_HEADER_NOT_ACCEPTED_AS_SE', 'row_index': 0,
    }]


@pytest.mark.parametrize('title', [
    'Weighted descriptive statistics',
    'Adjusted mean and standard error',
    'Repeated-measures summary',
    'Log-transformed values',
])
def test_weighted_adjusted_repeated_measure_and_transform_context_is_unsupported(title):
    table = _table_result(_document(title=title))

    assert table['applicability'] == 'APPLICABLE'
    assert table['eligibility'] == 'UNSUPPORTED'
    assert table['checked_rows'] == 0
    assert table['candidate_count'] == 0
    assert table['skip_reasons'] == [{'reason': 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY'}]


def test_cell_footnote_or_cross_reference_makes_row_incomplete():
    extra = (
        '<table-wrap-foot><fn id="fn1"><label>a</label><p>Values are weighted.</p></fn>'
        '</table-wrap-foot>'
    )
    source = (
        '<article><body><table-wrap id="T1"><table><thead><tr><th>Measure</th>'
        '<th>n</th><th>SD</th><th>SE</th></tr></thead><tbody><tr><th scope="row">Score</th>'
        '<td>4</td><td>6</td><td>3<xref ref-type="table-fn" rid="fn1">a</xref></td>'
        '</tr></tbody></table>' + extra + '</table-wrap></body></article>'
    ).encode('utf-8')
    table = _table_result(parse_jats(source, 'paper.xml'))

    assert table['eligibility'] == 'UNSUPPORTED'
    assert table['skip_reasons'] == [{'reason': 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY'}]
    assert table['candidate_count'] == 0


def test_unresolved_operand_footnote_suppresses_check_even_without_unsafe_note_text():
    source = (
        '<article><body><table-wrap id="T1"><table><thead><tr><th>Measure</th>'
        '<th>n</th><th>SD</th><th>SE</th></tr></thead><tbody><tr><th scope="row">Score</th>'
        '<td>4<xref ref-type="table-fn" rid="fn1">a</xref></td><td>6</td><td>3</td>'
        '</tr></tbody></table><table-wrap-foot><fn id="fn1"><label>a</label><p>See note.</p>'
        '</fn></table-wrap-foot></table-wrap></body></article>'
    ).encode('utf-8')
    table = _table_result(parse_jats(source, 'paper.xml'))

    assert table['eligibility'] == 'INCOMPLETE'
    assert table['skip_reasons'] == [{
        'reason': 'FOOTNOTE_CROSS_REFERENCE_OR_SCOPE_CUE_ON_ROW', 'row_index': 0,
    }]
    assert table['candidate_count'] == 0


def test_missing_and_duplicate_operand_columns_are_skipped():
    missing = _table_result(_document(headers=('n', 'SD'), values=('4', '6')))
    duplicate = _table_result(_document(
        headers=('n', 'n', 'SD', 'SE'), values=('4', '4', '6', '3'),
    ))

    assert missing['checked_rows'] == 0
    assert missing['skip_reasons'][0]['reason'] == 'MISSING_REQUIRED_OPERAND_COLUMN'
    assert duplicate['checked_rows'] == 0
    assert duplicate['skip_reasons'][0]['reason'] == 'DUPLICATE_OPERAND_COLUMNS'


def test_different_timepoint_or_unit_header_scope_is_not_compared():
    timepoints = _table_result(_document(
        grouped_headers=('Week 1', 'Week 1', 'Week 2'),
    ))
    units = _table_result(_document(
        grouped_headers=('Score (mm)', 'Score (mm)', 'Score (cm)'),
    ))

    assert timepoints['checked_rows'] == 0
    assert timepoints['skip_reasons'][0]['reason'] == 'OPERAND_SCOPE_OR_UNIT_HEADER_MISMATCH'
    assert units['checked_rows'] == 0
    assert units['skip_reasons'][0]['reason'] == 'OPERAND_SCOPE_OR_UNIT_HEADER_MISMATCH'


@pytest.mark.parametrize(
    ('values', 'reason'),
    [
        (('100000000000000000000000', '6', '3'), 'NUMERIC_TOKEN_TOO_LONG'),
        (('4', '1e100', '3'), 'SD_OR_SE_NOT_A_BOUNDED_DECIMAL'),
        (('4', '6', '0.123456789'), 'SD_OR_SE_NOT_A_BOUNDED_DECIMAL'),
        (('1000000001', '6', '3'), 'N_OUTSIDE_SUPPORTED_RANGE'),
    ],
)
def test_huge_and_pathological_numeric_cells_fail_closed(values, reason):
    table = _table_result(_document(values=values))

    assert table['checked_rows'] == 0
    assert table['candidate_count'] == 0
    assert table['skip_reasons'][0]['reason'] == reason


def test_unreliable_table_structure_is_not_checked():
    document = _document(extra='')
    table = document.tables[0]
    from dataclasses import replace

    document = replace(document, tables=(replace(table, structure_status='TABLE_STRUCTURE_UNSUPPORTED'),))
    result = _table_result(document)

    assert result['applicability'] == 'APPLICABLE'
    assert result['eligibility'] == 'UNSUPPORTED'
    assert result['checked_rows'] == 0
    assert result['skip_reasons'] == [{'reason': 'TABLE_STRUCTURE_NOT_RELIABLE'}]


def test_non_jats_document_is_not_treated_as_source_mapped_input():
    document = _document()
    from dataclasses import replace

    result = _table_result(replace(document, source_format='markdown'))

    assert result['eligibility'] == 'UNSUPPORTED'
    assert result['skip_reasons'] == [{'reason': 'SOURCE_FORMAT_NOT_JATS_XML'}]
