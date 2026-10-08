"""Coverage accounting stays scoped to represented source objects and detector outputs."""
from __future__ import annotations

from dataclasses import replace

import pytest

from researchwitness.jats import parse_jats
from researchwitness.paper_coverage import build_paper_coverage
from researchwitness.paper_ratio import check_jats_cell_ratio_percentages
from researchwitness.paper_statistics_source import check_jats_sd_se_n_tables
from researchwitness.table_arithmetic import check_structured_table_percentages


def _document(table_wraps: str):
    source = (
        '<article><front><article-meta><title-group><article-title>Coverage</article-title>'
        '</title-group></article-meta></front><body><sec><title>Results</title>'
        + table_wraps + '</sec></body></article>'
    ).encode('utf-8')
    return parse_jats(source)


def _table(table_contents: str, *, table_id: str = '') -> str:
    id_attribute = f' id="{table_id}"' if table_id else ''
    return (
        f'<table-wrap{id_attribute}><label>Table</label><caption><title>Outcomes</title></caption>'
        '<table><thead><tr><th>Outcome</th><th>All (N=20)</th></tr></thead><tbody>'
        + table_contents + '</tbody></table></table-wrap>'
    )


def test_jats_coverage_tracks_tables_operands_and_candidates_separately():
    document = _document(
        _table('<tr><th scope="row">Event</th><td>2 (8.0%)</td></tr>')
        + _table('<tr><th scope="row">Event</th><td>Not reported</td></tr>')
        + _table('<tr><th scope="row">Event (n=10)</th><td>2 (20.0%)</td></tr>')
    )
    results = check_structured_table_percentages(document)

    coverage = build_paper_coverage(document, results)
    assert coverage['paper']['tables'] == {
        'discovered': 3,
        'parsed': 3,
        'structure_reliable': 3,
        'structure_unsupported': 0,
        'parser_status_counts': {'STRUCTURE_RELIABLE': 3},
    }
    detector = coverage['detectors'][0]
    assert detector['status'] == 'ELIGIBLE'
    assert detector['status_counts'] == {
        'ELIGIBLE': 2,
        'NOT_APPLICABLE': 1,
    }
    assert detector['object_counts'] == {
        'unit': 'table',
        'potential': 3,
        'applicable': 2,
        'applicability_unknown': 0,
        'eligible': 2,
        'checked': 2,
        'skipped': 0,
        'candidates': 1,
    }
    assert detector['operand_counts'] == {
        'unit': 'count_percentage_cell',
        'potential': 2,
        'applicable': 2,
        'eligible': 2,
        'checked': 2,
        'skipped': 0,
        'candidates': 1,
    }
    assert [item['status'] for item in detector['tables']] == [
        'ELIGIBLE', 'NOT_APPLICABLE', 'ELIGIBLE',
    ]
    assert len({item['table_ref']['element_path'] for item in detector['tables']}) == 3
    assert all(item['table_ref']['source_sha256'] == document.source_sha256
               for item in detector['tables'])
    assert detector['tables'][1]['applicability'] == 'NOT_APPLICABLE'
    assert detector['tables'][2]['skip_reasons'] == []
    # The v1.3 row-local denominator is resolved before arithmetic, while the
    # unrelated non-numeric table remains NOT_APPLICABLE.
    assert detector['tables'][0]['counts']['operands']['candidates'] == 1
    assert detector['percentage_relation_telemetry_complete'] is True
    assert detector['percentage_relation_telemetry']['potential_relations'] == 2
    assert detector['percentage_relation_telemetry']['checked_mismatches'] == 1
    assert detector['percentage_relation_telemetry']['checked_matches'] == 1
    assert detector['percentage_relation_telemetry']['skipped_relations'] == 0
    assert detector['percentage_relation_telemetry']['primary_skip_reason_counts'] == {}


def test_duplicate_and_missing_table_ids_do_not_collide_in_source_references():
    document = _document(
        _table('<tr><th scope="row">A</th><td>1 (5%)</td></tr>')
        + _table('<tr><th scope="row">B</th><td>1 (5%)</td></tr>')
    )
    screen = check_structured_table_percentages(document)
    coverage = build_paper_coverage(document, screen)
    tables = coverage['detectors'][0]['tables']

    assert [table['table_id'] for table in tables] == ['', '']
    assert tables[0]['table_ref'] != tables[1]['table_ref']
    assert tables[0]['table_ref']['source_sha256'] == tables[1]['table_ref']['source_sha256']


def test_percentage_coverage_rejects_relations_swapped_between_duplicate_table_ids():
    import json
    document = _document(
        _table('<tr><th scope="row">A</th><td>1 (5%)</td></tr>')
        + _table('<tr><th scope="row">B</th><td>2 (10%)</td></tr>')
    )
    record = json.loads(json.dumps(check_structured_table_percentages(document)))
    record['tables'][0]['relations'], record['tables'][1]['relations'] = (
        record['tables'][1]['relations'], record['tables'][0]['relations'],
    )
    record['relations'] = record['tables'][0]['relations'] + record['tables'][1]['relations']

    detector = build_paper_coverage(document, record)['detectors'][0]

    assert detector['percentage_relation_telemetry_complete'] is False
    assert detector['percentage_relation_telemetry'] is None
    assert detector['status'] == 'INCOMPLETE'


def test_missing_detector_table_result_is_incomplete_and_counted_as_skipped():
    document = _document(
        _table('<tr><th scope="row">A</th><td>1 (5%)</td></tr>')
        + _table('<tr><th scope="row">B</th><td>1 (5%)</td></tr>')
    )
    record = {
        'detector_id': 'table_percentage_recomputation',
        'tables': [{
            'table_id': '', 'status': 'ELIGIBLE', 'reasons': [],
            'checked_cells': 1, 'candidate_count': 0,
        }],
    }

    detector = build_paper_coverage(document, record)['detectors'][0]
    assert detector['status'] == 'INCOMPLETE'
    assert detector['reasons'] == [
        'DETECTOR_TABLE_RESULT_COUNT_MISMATCH', 'PERCENTAGE_RELATION_TELEMETRY_INCOMPLETE',
    ]
    assert detector['tables'][1]['status'] == 'INCOMPLETE'
    assert detector['tables'][1]['skip_reasons'] == [
        'DETECTOR_TABLE_RESULT_MISSING', 'PERCENTAGE_RELATION_TELEMETRY_INCOMPLETE',
    ]
    assert detector['object_counts']['potential'] == 2
    assert detector['object_counts']['skipped'] is None
    assert detector['operand_counts']['skipped'] is None
    assert detector['object_counts']['candidates'] is None
    assert detector['percentage_relation_telemetry_complete'] is False
    assert detector['percentage_relation_telemetry'] is None


def test_missing_direct_detector_row_uses_direct_ratio_shape_and_withholds_totals():
    document = _document(
        '<table-wrap><table><thead><tr><th>Outcome</th><th>n/N (%)</th></tr></thead><tbody>'
        '<tr><th scope="row">Event</th><td>11/20 (55%)</td></tr>'
        '</tbody></table></table-wrap>'
    )
    detector = build_paper_coverage(document, {
        'detector_id': 'jats_cell_ratio_percentage_recomputation',
        'tables': [],
    })['detectors'][0]

    assert detector['status'] == 'INCOMPLETE'
    assert detector['operand_counts']['potential'] == 1
    assert detector['operand_counts']['checked'] is None
    assert detector['tables'][0]['counts']['operands']['potential'] == 1
    assert detector['percentage_relation_telemetry'] is None


def test_direct_ratio_coverage_uses_relation_semantics_when_table_grid_is_unsupported():
    document = _document(
        '<table-wrap><table><thead><tr><th>Outcome</th><th>n/N (%)</th></tr></thead><tbody>'
        '<tr><th scope="row">Event</th><td>11/20 (55%)</td></tr>'
        '</tbody></table></table-wrap>'
    )
    table = document.tables[0]
    document = replace(
        document,
        tables=(replace(table, structure_status='TABLE_STRUCTURE_UNSUPPORTED'),),
    )

    screen = check_jats_cell_ratio_percentages(document)
    detector = build_paper_coverage(document, screen)['detectors'][0]

    assert screen['tables'][0]['status'] == 'ELIGIBLE'
    assert detector['percentage_relation_telemetry_complete'] is True
    assert detector['percentage_relation_telemetry']['checked_matches'] == 1
    assert detector['status'] == 'ELIGIBLE'
    assert detector['tables'][0]['parser_status'] == 'TABLE_STRUCTURE_UNSUPPORTED'
    assert detector['tables'][0]['status'] == 'ELIGIBLE'


def test_direct_finding_cap_marks_table_incomplete_without_skipping_checked_relation(monkeypatch):
    from researchwitness import paper_ratio

    monkeypatch.setattr(paper_ratio, 'MAX_RATIO_FINDINGS', 0)
    document = _document(
        '<table-wrap><table><thead><tr><th>Outcome</th><th>n/N (%)</th></tr></thead><tbody>'
        '<tr><th scope="row">Event</th><td>11/20 (50%)</td></tr>'
        '</tbody></table></table-wrap>'
    )

    screen = check_jats_cell_ratio_percentages(document)
    detector = build_paper_coverage(document, screen)['detectors'][0]

    assert screen['candidate_findings_omitted'] == 1
    assert screen['relations'][0]['status'] == 'ELIGIBLE_CHECKED_MISMATCH'
    assert screen['relations'][0]['finding_emitted'] is False
    assert detector['percentage_relation_telemetry_complete'] is True
    assert detector['percentage_relation_telemetry']['checked_mismatches'] == 1
    assert detector['percentage_relation_telemetry']['skipped_relations'] == 0
    assert detector['status'] == 'INCOMPLETE'
    table_coverage = detector['tables'][0]
    assert table_coverage['status'] == 'INCOMPLETE'
    assert table_coverage['candidate_findings_omitted'] == 1
    assert table_coverage['counts']['operands']['checked'] == 1
    assert table_coverage['counts']['operands']['skipped'] == 0
    assert 'CANDIDATE_FINDINGS_OMITTED' in table_coverage['reasons']


def test_percentage_coverage_rejects_inconsistent_relation_telemetry_summary():
    document = _document(_table('<tr><th scope="row">A</th><td>1 (5%)</td></tr>'))
    screen = check_structured_table_percentages(document)
    import json
    screen = json.loads(json.dumps(screen))
    screen['relation_telemetry']['checked_matches'] = 0

    detector = build_paper_coverage(document, screen)['detectors'][0]

    assert detector['percentage_relation_telemetry_complete'] is False
    assert detector['percentage_relation_telemetry'] is None
    assert detector['status'] == 'INCOMPLETE'
    assert detector['operand_counts']['checked'] is None


def test_percentage_coverage_rejects_altered_per_table_relation_and_counters():
    import json
    document = _document(_table('<tr><th scope="row">A</th><td>1 (5%)</td></tr>'))
    original = check_structured_table_percentages(document)

    altered_relation = json.loads(json.dumps(original))
    altered_relation['tables'][0]['relations'][0]['status'] = 'ELIGIBLE_CHECKED_MISMATCH'
    altered_relation['tables'][0]['relations'][0]['primary_skip_reason'] = None
    altered_relation['tables'][0]['relations'][0]['secondary_skip_reasons'] = []
    altered_counter = json.loads(json.dumps(original))
    altered_counter['tables'][0]['checked_cells'] = 0

    for record in (altered_relation, altered_counter):
        detector = build_paper_coverage(document, record)['detectors'][0]
        assert detector['percentage_relation_telemetry_complete'] is False
        assert detector['percentage_relation_telemetry'] is None
        assert detector['status'] == 'INCOMPLETE'
        assert detector['operand_counts']['checked'] is None


def test_paper_scoped_coverage_preserves_status_and_unknown_counts():
    document = _document(_table('<tr><th scope="row">A</th><td>1 (5%)</td></tr>'))
    record = {
        'detector_id': 'narrative_flow',
        'status': 'UNSUPPORTED',
        'reasons': ['SOURCE_NATIVE_ANCHOR_UNAVAILABLE'],
        'potential_objects': 4,
        'checked_operands': 0,
    }

    detector = build_paper_coverage(document, [record])['detectors'][0]
    assert detector['scope'] == 'paper'
    assert detector['status'] == 'UNSUPPORTED'
    assert detector['object_counts'] == {
        'unit': 'detector_object',
        'potential': 4,
        'applicable': None,
        'eligible': None,
        'checked': None,
        'skipped': None,
        'candidates': None,
    }
    assert detector['operand_counts']['checked'] == 0


def test_detector_order_is_deterministic_and_no_table_screen_is_unsupported():
    document = _document('')
    no_tables = check_structured_table_percentages(document)
    flow = {
        'detector_id': 'explicit_exclusion_flow_locator',
        'status': 'NOT_APPLICABLE',
        'reasons': ['NO_FLOW_SHAPED_SENTENCE_FOUND'],
    }
    first = build_paper_coverage(document, [flow, no_tables])
    second = build_paper_coverage(document, [no_tables, flow])

    assert first == second
    assert [item['detector_id'] for item in first['detectors']] == [
        'explicit_exclusion_flow_locator', 'table_percentage_recomputation',
    ]
    assert first['detectors'][1]['status'] == 'UNSUPPORTED'
    assert first['detectors'][1]['reasons'] == ['NO_JATS_TABLES_FOUND']


def test_invalid_or_misaligned_detector_results_fail_closed():
    document = _document(_table('<tr><th scope="row">A</th><td>1 (5%)</td></tr>'))

    with pytest.raises(ValueError, match='identity differs'):
        build_paper_coverage(document, {
            'detector_id': 'table_percentage_recomputation',
            'tables': [{
                'table_id': 'wrong-table', 'status': 'ELIGIBLE',
                'checked_cells': 1, 'candidate_count': 0,
            }],
        })


def test_detector_supplied_operands_keep_ratio_cells_and_summary_rows_distinct():
    ratio_table = (
        '<table-wrap id="ratio"><label>Table R</label><caption><title>Disposition</title></caption>'
        '<table><thead><tr><th>Outcome</th><th>n/N (%)</th></tr></thead><tbody>'
        '<tr><th scope="row">Transferred</th><td>11/233 (1.8%)</td></tr>'
        '</tbody></table></table-wrap>'
    )
    statistics_table = (
        '<table-wrap id="summary"><label>Table S</label><caption><title>Summary statistics</title></caption>'
        '<table><thead><tr><th>Measure</th><th>n</th><th>SD</th><th>SE</th></tr></thead><tbody>'
        '<tr><th scope="row">Score</th><td>4</td><td>6</td><td>2.9</td></tr>'
        '</tbody></table></table-wrap>'
    )
    document = _document(ratio_table + statistics_table)
    ratio = check_jats_cell_ratio_percentages(document)
    statistics = check_jats_sd_se_n_tables(document)

    coverage = build_paper_coverage(document, [ratio, statistics])
    detectors = {item['detector_id']: item for item in coverage['detectors']}
    ratio_coverage = detectors['jats_cell_ratio_percentage_recomputation']
    statistics_coverage = detectors['jats_sd_se_n_recomputation']

    assert ratio_coverage['operand_counts']['unit'] == 'n_over_N_percent_cell'
    assert ratio_coverage['operand_counts']['potential'] == 1
    assert ratio_coverage['operand_counts']['checked'] == 1
    assert [item['status'] for item in ratio_coverage['tables']] == ['ELIGIBLE', 'NOT_APPLICABLE']
    assert statistics_coverage['operand_counts']['unit'] == 'eligible_sd_se_n_row'
    assert statistics_coverage['operand_counts']['potential'] == 1
    assert statistics_coverage['operand_counts']['checked'] == 1
    assert [item['status'] for item in statistics_coverage['tables']] == ['NOT_APPLICABLE', 'ELIGIBLE']
