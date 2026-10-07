"""Candidate adjudication metrics keep version certainty separate from arithmetic validity."""
from __future__ import annotations

import json

from tools.run_paper_audit_percentage_qualification import (
    _candidate_adjudication_metrics,
    _negative_locator_matches,
    _pair_negative_source_relations,
    _negative_source_table_ids,
)


def test_version_unverified_source_discrepancies_count_as_arithmetic_validity(tmp_path):
    classifications = [
        'SOURCE_REPRODUCED_KNOWN_CORRECTION_TARGET',
        'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY',
        'SOURCE_REPRODUCED_ARITHMETIC_DISCREPANCY_VERSION_UNVERIFIED',
        'SCOPE_DENOMINATOR_NOT_EXPLICIT',
    ]
    rows = []
    items = []
    for index, classification in enumerate(classifications, start=1):
        case_id = f'paper-{index:03d}'
        candidate_id = f'candidate-{index:04d}'
        source_hash = f'{index:064x}'
        report_hash = f'{index + 10:064x}'
        facts = {
            'id': candidate_id,
            'relation_id': f'{index + 20:064x}',
            'table_id': 'Tab1',
            'row_identity': f'Row {index}',
            'numerator_exact': '1',
            'denominator_exact': '3',
            'reported_percent': '34',
            'display_precision': 0,
            'recomputed_at_display_precision': '33',
            'anchor_paths': [f'/article[1]/table-wrap[1]/tbody[1]/tr[{index}]/td[1]'],
        }
        rows.append({
            'case_id': case_id,
            'source_sha256': source_hash,
            'report_sha256': report_hash,
            'candidate_ids': [candidate_id],
            'candidate_records': [facts],
            'candidate_count': 1,
        })
        items.append({
            'case_id': case_id,
            'candidate_id': candidate_id,
            'source_sha256': source_hash,
            'report_sha256': report_hash,
            'relation_id': facts['relation_id'],
            'table_id': facts['table_id'],
            'row_identity': facts['row_identity'],
            'numerator': facts['numerator_exact'],
            'denominator': facts['denominator_exact'],
            'reported_percent': facts['reported_percent'],
            'display_precision_digits': facts['display_precision'],
            'recomputed_at_display_precision': facts['recomputed_at_display_precision'],
            'anchors': facts['anchor_paths'],
            'classification': classification,
        })

    review_path = tmp_path / 'candidate-review.json'
    review_path.write_text(json.dumps({
        'status': 'POST_HOC_DEVELOPMENT_SOURCE_ADJUDICATION',
        'percentage_contract_version': '1.2',
        'items': items,
    }), encoding='utf-8')

    metrics = _candidate_adjudication_metrics(review_path, rows)

    assert metrics['candidate_arithmetic_validity'] == {'numerator': 3, 'denominator': 4}
    assert metrics['known_correction_target_share'] == {'numerator': 1, 'denominator': 4}
    assert metrics['source_reproduced_uncorrected_non_target_discrepancies'] == 1
    assert metrics['source_reproduced_version_status_unverified_discrepancies'] == 1
    assert metrics['scope_denominator_not_explicit_candidates'] == 1
    assert metrics['all_current_candidates_adjudicated'] is True


def test_negative_join_disambiguates_relations_with_a_shared_paragraph_anchor():
    first = {
        'numerator_exact': '3',
        'denominator_exact': '19',
        'reported_percent': '15.8',
        'display_precision': 1,
    }
    second = {
        'numerator_exact': '1',
        'denominator_exact': '19',
        'reported_percent': '5.3',
        'display_precision': 1,
    }
    shared_locator = {
        'numerator': '1',
        'denominator': '19',
        'reported_percent': '5.3',
        'display_precision_digits': 1,
    }

    assert not _negative_locator_matches(first, shared_locator)
    assert _negative_locator_matches(second, shared_locator)


def test_negative_join_keeps_unique_anchor_candidate_when_parsed_denominator_differs():
    locator = {
        'contract_id': 'table_percentage_recomputation',
        'cell_path': '/article[1]/table-wrap[1]/tbody[1]/tr[1]/td[2]',
        'numerator': '4',
        'denominator': '6',
        'reported_percent': '67',
        'display_precision_digits': 0,
    }
    relation = {
        'detector_id': 'table_percentage_recomputation',
        'source_anchor': {
            'element_path': locator['cell_path'],
            'source_sha256': 'a' * 64,
        },
        'numerator_exact': '4',
        'denominator_exact': '30',
        'reported_percent': '67',
        'display_precision': 0,
        'status': 'ELIGIBLE_CHECKED_MISMATCH',
        'finding_emitted': True,
    }

    assert _pair_negative_source_relations([locator], [relation]) == [(relation, False)]


def test_negative_join_keeps_wrong_operand_match_out_of_exact_coverage():
    locator = {
        'contract_id': 'table_percentage_recomputation',
        'cell_path': '/article[1]/table-wrap[1]/tbody[1]/tr[1]/td[2]',
        'numerator': '0',
        'denominator': '3',
        'reported_percent': '0',
        'display_precision_digits': 0,
    }
    relation = {
        'detector_id': 'table_percentage_recomputation',
        'source_anchor': {'element_path': locator['cell_path']},
        'numerator_exact': '0',
        'denominator_exact': '5',
        'reported_percent': '0',
        'display_precision': 0,
        'status': 'ELIGIBLE_CHECKED_MATCH',
        'finding_emitted': False,
    }

    assert _pair_negative_source_relations([locator], [relation]) == [(relation, False)]


def test_negative_join_resolves_multiple_same_anchor_relations_before_unique_fallback():
    path = '/article[1]/p[1]'
    first = {
        'contract_id': 'jats_cell_ratio_percentage_recomputation',
        'cell_path': path,
        'numerator': '3',
        'denominator': '19',
        'reported_percent': '15.8',
        'display_precision_digits': 1,
    }
    second = {
        **first,
        'numerator': '1',
        'reported_percent': '5.3',
    }
    exact_first = {
        'detector_id': first['contract_id'],
        'source_anchor': {'element_path': path},
        'numerator_exact': '3',
        'denominator_exact': '19',
        'reported_percent': '15.8',
        'display_precision': 1,
    }
    wrong_parse_for_second = {
        **exact_first,
        'numerator_exact': '1',
        'denominator_exact': '20',
        'reported_percent': '5.3',
    }

    assert _pair_negative_source_relations(
        [first, second], [exact_first, wrong_parse_for_second],
    ) == [(exact_first, True), (wrong_parse_for_second, False)]


def test_negative_join_does_not_guess_between_ambiguous_same_anchor_relations():
    path = '/article[1]/p[1]'
    locators = [
        {
            'contract_id': 'jats_cell_ratio_percentage_recomputation',
            'cell_path': path,
            'numerator': str(numerator),
            'denominator': '19',
            'reported_percent': str(percent),
            'display_precision_digits': 1,
        }
        for numerator, percent in ((3, '15.8'), (1, '5.3'))
    ]
    relation = {
        'detector_id': locators[0]['contract_id'],
        'source_anchor': {'element_path': path},
        'numerator_exact': '2',
        'denominator_exact': '20',
        'reported_percent': '10.0',
        'display_precision': 1,
    }

    assert _pair_negative_source_relations(locators, [relation]) == [
        (None, False), (None, False),
    ]


def test_negative_source_table_count_excludes_prose_relations():
    source = {
        'relation_locators': [
            {'table_id': 'Tab1'},
            {'table_id': 'Tab1'},
            {'table_id': None},
        ],
    }

    assert _negative_source_table_ids(source) == {'Tab1'}
