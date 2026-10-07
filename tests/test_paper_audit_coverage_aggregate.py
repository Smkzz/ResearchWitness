import pytest

from researchwitness.paper_relation_telemetry import summarize_relations
from tools.run_paper_audit_percentage_qualification import (
    _aggregate_detector_coverage,
    _aggregate_percentage_relation_telemetry,
)


def test_coverage_aggregate_preserves_table_reasons_by_status():
    rows = [{
        'coverage': {
            'detectors': [{
                'detector_id': 'table_percentage_recomputation',
                'status': 'INCOMPLETE',
                'object_counts': {},
                'operand_counts': {},
                'status_counts': {},
                'reason_codes': {'DETECTOR_LEVEL_REASON': 2},
                'tables': [
                    {'status': 'INCOMPLETE', 'parser_status': 'STRUCTURE_RELIABLE',
                     'reason_codes': ['LOCAL_DENOMINATOR', 'FOOTNOTE_SCOPE_UNRESOLVED',
                                      'DUPLICATE_OPERAND_COLUMNS (row 0)']},
                    {'status': 'UNSUPPORTED', 'parser_status': 'STRUCTURE_RELIABLE',
                     'reason_codes': ['WEIGHTED_OR_ADJUSTED']},
                    {'status': 'INCOMPLETE', 'parser_status': 'TABLE_STRUCTURE_UNSUPPORTED',
                     'reason_codes': ['LOCAL_DENOMINATOR', 'DUPLICATE_OPERAND_COLUMNS (row 1)']},
                ],
            }],
        },
    }]

    [summary] = _aggregate_detector_coverage(rows)

    assert summary['skip_reason_counts'] == {'DETECTOR_LEVEL_REASON': 2}
    assert summary['table_reason_counts_by_status'] == {
        'INCOMPLETE': {
            'DUPLICATE_OPERAND_COLUMNS': 2,
            'FOOTNOTE_SCOPE_UNRESOLVED': 1,
            'LOCAL_DENOMINATOR': 2,
        },
        'UNSUPPORTED': {'WEIGHTED_OR_ADJUSTED': 1},
    }
    assert summary['table_reason_count_unit'] == (
        'normalized reason strings per table result, grouped by table status'
    )


def test_percentage_coverage_aggregate_checks_every_partition_equation():
    telemetry = summarize_relations([
        {
            'relation_id': 'match', 'status': 'ELIGIBLE_CHECKED_MATCH',
            'primary_skip_reason': None, 'secondary_skip_reasons': [],
        },
        {
            'relation_id': 'skip', 'status': 'INCOMPLETE',
            'primary_skip_reason': 'FOOTNOTE_SCOPE_UNRESOLVED', 'secondary_skip_reasons': [],
        },
    ])

    [summary] = [_aggregate_percentage_relation_telemetry([
        {'coverage': {'percentage_relation_telemetry': telemetry}},
    ])]
    assert summary['potential_relations'] == 2
    assert summary['applicable_relations'] == 2
    assert summary['eligible_relations'] == 1
    assert summary['checked_relations'] == 1
    assert summary['skipped_relations'] == 1
    assert summary['primary_skip_reason_counts'] == {'FOOTNOTE_SCOPE_UNRESOLVED': 1}

    inconsistent = dict(telemetry)
    inconsistent['skipped_relations'] = 0
    with pytest.raises(ValueError, match='frozen partition equations'):
        _aggregate_percentage_relation_telemetry([
            {'coverage': {'percentage_relation_telemetry': inconsistent}},
        ])
