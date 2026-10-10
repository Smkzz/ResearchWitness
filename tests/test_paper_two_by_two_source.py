"""Hard negatives for source-mapped unadjusted 2x2 odds ratios."""
from __future__ import annotations

from dataclasses import replace

import pytest

from researchwitness.jats import parse_jats
import researchwitness.paper_two_by_two_source as two_by_two
from researchwitness.paper_two_by_two_source import check_jats_unadjusted_2x2_tables


HEADERS = (
    'Outcome', 'Exposed event', 'Exposed non-event', 'Unexposed event',
    'Unexposed non-event', 'Unadjusted odds ratio (exposed vs unexposed)',
)
VALUES = ('30-day mortality', '12', '88', '6', '94', '2.14')


def _document(*, headers=HEADERS, values=VALUES, caption='2x2 mortality at 30 days'):
    assert len(headers) == len(values)
    header_cells = ''.join(f'<th>{value}</th>' for value in headers)
    row_cells = '<th scope="row">' + values[0] + '</th>' + ''.join(
        f'<td>{value}</td>' for value in values[1:]
    )
    source = (
        '<article><body><table-wrap id="T1"><label>Table 1</label>'
        f'<caption><title>{caption}</title></caption><table><thead><tr>{header_cells}</tr></thead>'
        f'<tbody><tr>{row_cells}</tr></tbody></table></table-wrap></body></article>'
    ).encode('utf-8')
    return parse_jats(source, 'paper.xml')


def _table(document):
    return check_jats_unadjusted_2x2_tables(document)['tables'][0]


def test_explicit_unadjusted_or_returns_exact_cells_and_five_anchors():
    document = _document()
    report = check_jats_unadjusted_2x2_tables(document)

    assert report['scan_complete'] is True
    assert report['tables'][0]['status'] == 'ELIGIBLE'
    assert report['tables'][0]['checked_objects'] == 1
    check = report['tables'][0]['checks'][0]
    assert check['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert check['exact_numerator'] == '47'
    assert check['exact_denominator'] == '22'
    assert len(check['source_anchors']) == 5
    assert all(anchor['source_sha256'] == document.source_sha256 for anchor in check['source_anchors'])


def test_mismatch_is_candidate_with_all_four_cells_and_reported_stat_anchored():
    values = ('30-day mortality', '12', '88', '6', '94', '2.20')
    report = check_jats_unadjusted_2x2_tables(_document(values=values))

    assert len(report['findings']) == 1
    candidate = report['findings'][0]
    assert candidate['type'] == 'JATS_UNADJUSTED_2X2_ODDS_RATIO_MISMATCH'
    assert candidate['recomputed_at_display_precision'] == '2.14'
    assert [anchor['quote'] for anchor in candidate['source_anchors'][:4]] == ['12', '88', '6', '94']
    assert candidate['source_anchors'][4]['quote'] == '2.20'


@pytest.mark.parametrize('header', [
    'Adjusted odds ratio (exposed vs unexposed)',
    'Unadjusted odds ratio',
    'Unadjusted odds ratio (unexposed vs exposed)',
])
def test_adjusted_or_missing_or_reversed_orientation_is_not_checked(header):
    headers = (*HEADERS[:5], header)
    table = _table(_document(headers=headers))

    assert table['status'] == 'UNSUPPORTED'
    assert table['checked_objects'] == 0
    assert table['candidate_count'] == 0


def test_zero_cells_follow_explicit_unsupported_boundary():
    table = _table(_document(values=('30-day mortality', '0', '100', '6', '94', '0.00')))

    assert table['status'] == 'UNSUPPORTED'
    assert table['skip_reasons'] == [{'reason': 'ZERO_CELL_POLICY_UNSPECIFIED', 'row_index': 0}]


def test_missing_timepoint_or_weighting_context_is_skipped():
    missing_time = _table(_document(values=('mortality', *VALUES[1:])))
    weighted = _table(_document(caption='Weighted 2x2 mortality at 30 days'))

    assert missing_time['status'] == 'UNSUPPORTED'
    assert missing_time['skip_reasons'][0]['reason'] == 'TIMEPOINT_UNSPECIFIED'
    assert weighted['status'] == 'UNSUPPORTED'
    assert weighted['skip_reasons'][0]['reason'] == 'MODEL_ADJUSTED_WEIGHTED_OR_COMPLEX_CONTEXT'


@pytest.mark.parametrize('cue', [
    'standardize', 'standardise', 'standardizing', 'standardising',
])
def test_standardization_morphology_makes_two_by_two_result_unsupported(cue):
    table = _table(_document(caption=f'{cue} estimates at 30 days'))

    assert table['status'] == 'UNSUPPORTED'
    assert table['checked_objects'] == 0


def test_ci_or_noninteger_count_cells_are_not_parsed():
    ci = _table(_document(values=(*VALUES[:-1], '2.14 (1.10-4.20)')))
    decimal_count = _table(_document(values=(*VALUES[:1], '12.5', *VALUES[2:])))

    assert ci['status'] == 'INCOMPLETE'
    assert ci['skip_reasons'][0]['reason'] == 'REPORTED_ODDS_RATIO_NOT_EXPLICIT_DECIMAL'
    assert decimal_count['status'] == 'INCOMPLETE'
    assert decimal_count['skip_reasons'][0]['reason'] == '2X2_COUNT_NOT_EXPLICIT_INTEGER'


def test_multiple_rows_are_not_joined_or_compared_as_one_table():
    source = (
        '<article><body><table-wrap><caption><title>2x2 table</title></caption><table>'
        '<thead><tr>' + ''.join(f'<th>{item}</th>' for item in HEADERS) + '</tr></thead><tbody>'
        + ''.join('<tr><th scope="row">' + values[0] + '</th>' + ''.join(
            f'<td>{value}</td>' for value in values[1:]
        ) + '</tr>' for values in (VALUES, VALUES))
        + '</tbody></table></table-wrap></body></article>'
    ).encode('utf-8')
    table = _table(parse_jats(source, 'paper.xml'))

    assert table['status'] == 'INCOMPLETE'
    assert table['skip_reasons'][0]['reason'] == 'ONE_OUTCOME_ROW_REQUIRED'


def test_candidate_limit_is_reported_as_incomplete_coverage(monkeypatch):
    document = _document(values=('30-day mortality', '12', '88', '6', '94', '2.20'))
    # Two candidate-producing tables exercise the report cap without building
    # an unnecessarily large synthetic JATS document.
    document = replace(document, tables=document.tables * 2)
    monkeypatch.setattr(two_by_two, 'MAX_FINDINGS', 1)

    report = check_jats_unadjusted_2x2_tables(document)

    assert len(report['findings']) == 1
    assert report['scan_complete'] is False
    omitted = report['tables'][1]
    assert omitted['status'] == 'INCOMPLETE'
    assert omitted['checked_objects'] == 0
    assert omitted['skipped_objects'] == 1
    assert omitted['candidate_count'] == 0
    assert omitted['checks'] == []
    assert omitted['skip_reasons'] == [{'reason': '2X2_CANDIDATE_LIMIT'}]
