from tools.run_paper_audit_capability_wave_2 import _aggregate_detector_coverage


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
