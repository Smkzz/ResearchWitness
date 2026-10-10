from __future__ import annotations

import pytest
from hashlib import sha256

from researchwitness.paper_relation_telemetry import (
    relation_id,
    summarize_relations,
    terminal_relation,
)


_SOURCE = {'source_file': 'source.xml', 'source_sha256': 'a' * 64, 'element_path': '/cell[1]'}
_TABLE_SOURCE_V13 = {
    'source_file': 'source.xml', 'source_sha256': 'a' * 64, 'source_format': 'jats_xml',
    'element_path': '/article[1]/body[1]/table-wrap[1]', 'quote': '',
}
_RELATION_SOURCE_V13 = {
    'source_file': 'source.xml', 'source_sha256': 'a' * 64, 'source_format': 'jats_xml',
    'element_path': '/article[1]/body[1]/table-wrap[1]/table[1]/tbody[1]/tr[1]/td[1]', 'quote': '',
}
_DENOMINATOR_SOURCE_V13 = {
    'source_file': 'source.xml', 'source_sha256': 'a' * 64, 'source_format': 'jats_xml',
    'element_path': '/article[1]/body[1]/table-wrap[1]/table[1]/thead[1]/tr[1]/th[2]', 'quote': '',
}
_TABLE_KEY_V13 = sha256(
    (_TABLE_SOURCE_V13['source_sha256'] + '\0' + _TABLE_SOURCE_V13['element_path']).encode('utf-8')
).hexdigest()


def _relation(identifier: str, status: str, *reasons: str):
    return terminal_relation(
        relation_id_value=identifier,
        relation_type='CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
        detector_id='table_percentage_recomputation',
        contract_version='1.2',
        table_key='b' * 64,
        source_anchor=_SOURCE,
        status=status,
        reasons=reasons,
    )


def test_relation_ids_bind_version_source_cell_and_detector_without_row_labels():
    base = relation_id('table_percentage_recomputation', '1.2', 'a' * 64, '/cell[1]')

    assert base == relation_id('table_percentage_recomputation', '1.2', 'a' * 64, '/cell[1]')
    assert base != relation_id('table_percentage_recomputation', '1.1', 'a' * 64, '/cell[1]')
    assert base != relation_id('table_percentage_recomputation', '1.2', 'c' * 64, '/cell[1]')
    assert base != relation_id('jats_cell_ratio_percentage_recomputation', '1.2', 'a' * 64, '/cell[1]')


def test_primary_skip_reasons_partition_skipped_relations_once():
    records = [
        _relation('1', 'NOT_APPLICABLE'),
        _relation('2', 'ELIGIBLE_CHECKED_MATCH'),
        _relation('3', 'ELIGIBLE_CHECKED_MISMATCH'),
        _relation('4', 'INCOMPLETE', 'MULTIPLE_RESPONSE', 'FOOTNOTE_SCOPE_UNRESOLVED'),
        _relation('5', 'UNSUPPORTED', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'),
    ]

    summary = summarize_relations(records)

    assert summary['potential_relations'] == 5
    assert summary['applicable_relations'] == 4
    assert summary['eligible_relations'] == 2
    assert summary['checked_matches'] == 1
    assert summary['checked_mismatches'] == 1
    assert summary['skipped_relations'] == 2
    assert sum(summary['primary_skip_reason_counts'].values()) == summary['skipped_relations']
    assert summary['primary_skip_reason_counts'] == {
        'FOOTNOTE_SCOPE_UNRESOLVED': 1,
        'GROUPED_INTEGER_FORMAT_UNSUPPORTED': 1,
    }
    assert summary['secondary_skip_reason_counts_overlapping'] == {'MULTIPLE_RESPONSE': 1}
    assert summary['accounting_invariant'] is True


def test_duplicate_relation_ids_and_missing_primary_reasons_fail_closed():
    valid = _relation('duplicate', 'INCOMPLETE', 'DENOMINATOR_NOT_EXPLICIT')

    with pytest.raises(ValueError, match='identities must be unique'):
        summarize_relations([valid, valid])
    with pytest.raises(ValueError, match='require a primary reason'):
        terminal_relation(
            relation_id_value='missing',
            relation_type='DIRECT_N_OVER_N_PERCENTAGE',
            detector_id='jats_cell_ratio_percentage_recomputation',
            contract_version='1.2',
            table_key='b' * 64,
            source_anchor=_SOURCE,
            status='UNSUPPORTED',
        )
    with pytest.raises(ValueError, match='only skipped'):
        terminal_relation(
            relation_id_value='checked',
            relation_type='DIRECT_N_OVER_N_PERCENTAGE',
            detector_id='jats_cell_ratio_percentage_recomputation',
            contract_version='1.2',
            table_key='b' * 64,
            source_anchor=_SOURCE,
            status='ELIGIBLE_CHECKED_MATCH',
            reasons=['DENOMINATOR_NOT_EXPLICIT'],
        )


def _v13_relation(
    status='ELIGIBLE_CHECKED_MATCH', *, scope_resolved=True, value='20',
    denominator_source_sha='a' * 64, denominator_path=None,
    relation_source_sha='a' * 64, relation_path=None, table_key=None,
):
    selected_anchor = dict(_DENOMINATOR_SOURCE_V13)
    selected_anchor['source_sha256'] = denominator_source_sha
    if denominator_path is not None:
        selected_anchor['element_path'] = denominator_path
    selected = {'value_exact': value, 'source_anchor': selected_anchor} if scope_resolved else None
    provenance = {
        'resolution_status': 'RESOLVED' if scope_resolved else 'UNRESOLVED',
        'selected_denominator': selected,
    }
    details = {
        'denominator_scope_resolved': scope_resolved,
        'denominator_provenance': provenance,
        'denominator_source_anchor': selected_anchor if scope_resolved else None,
    }
    if status in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH'):
        details.update({'numerator_exact': '4', 'denominator_exact': value})
    relation_anchor = dict(_RELATION_SOURCE_V13)
    relation_anchor['source_sha256'] = relation_source_sha
    if relation_path is not None:
        relation_anchor['element_path'] = relation_path
    return terminal_relation(
        relation_id_value='v13',
        relation_type='CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
        detector_id='table_percentage_recomputation',
        contract_version='1.3',
        table_key=_TABLE_KEY_V13 if table_key is None else table_key,
        source_anchor=relation_anchor,
        status=status,
        reasons=['DENOMINATOR_NOT_EXPLICIT'] if status == 'INCOMPLETE' else (),
        table_source_anchor=_TABLE_SOURCE_V13,
        **details,
    )


def test_v1_3_checked_status_requires_resolved_source_and_exact_selected_value():
    record = _v13_relation()
    assert record['denominator_scope_resolved'] is True

    with pytest.raises(ValueError, match='arithmetic status requires'):
        _v13_relation(scope_resolved=False)

    with pytest.raises(ValueError, match='must match the selected provenance value'):
        terminal_relation(
            relation_id_value='wrong-value',
            relation_type='CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
            detector_id='table_percentage_recomputation',
            contract_version='1.3',
            table_key=_TABLE_KEY_V13,
            source_anchor=_RELATION_SOURCE_V13,
            status='ELIGIBLE_CHECKED_MATCH',
            numerator_exact='0',
            denominator_exact='100',
            denominator_scope_resolved=True,
            denominator_source_anchor=_DENOMINATOR_SOURCE_V13,
            denominator_provenance={
                'resolution_status': 'RESOLVED',
                'selected_denominator': {
                    'value_exact': '20',
                    'source_anchor': _DENOMINATOR_SOURCE_V13,
                },
            },
            table_source_anchor=_TABLE_SOURCE_V13,
        )


def test_v1_3_selected_denominator_must_share_source_hash_and_table_path():
    with pytest.raises(ValueError, match='same source table'):
        _v13_relation(denominator_source_sha='c' * 64)
    with pytest.raises(ValueError, match='same source table'):
        _v13_relation(denominator_path=(
            '/article[1]/body[1]/table-wrap[2]/table[1]/thead[1]/tr[1]/th[2]'
        ))


def test_v1_3_relation_anchor_and_table_key_must_bind_the_table():
    with pytest.raises(ValueError, match='relation anchor must belong to the same source table'):
        _v13_relation(relation_source_sha='c' * 64)
    with pytest.raises(ValueError, match='relation anchor must belong to the same source table'):
        _v13_relation(relation_path=(
            '/article[1]/body[1]/table-wrap[2]/table[1]/tbody[1]/tr[1]/td[1]'
        ))
    with pytest.raises(ValueError, match='table key must bind'):
        _v13_relation(table_key='b' * 64)


def test_v1_3_unresolved_scope_cannot_retain_a_selected_denominator():
    with pytest.raises(ValueError, match='cannot contain a selected denominator'):
        terminal_relation(
            relation_id_value='unresolved-selection',
            relation_type='CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
            detector_id='table_percentage_recomputation',
            contract_version='1.3',
            table_key=_TABLE_KEY_V13,
            source_anchor=_RELATION_SOURCE_V13,
            status='INCOMPLETE',
            reasons=['DENOMINATOR_AMBIGUOUS'],
            denominator_scope_resolved=False,
            denominator_source_anchor=_DENOMINATOR_SOURCE_V13,
            denominator_provenance={
                'resolution_status': 'AMBIGUOUS',
                'selected_denominator': {'value_exact': '20'},
            },
            table_source_anchor=_TABLE_SOURCE_V13,
        )


def test_v1_3_unresolved_scope_cannot_retain_a_denominator_anchor():
    with pytest.raises(ValueError, match='cannot contain a denominator anchor'):
        terminal_relation(
            relation_id_value='orphan-anchor',
            relation_type='CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
            detector_id='table_percentage_recomputation',
            contract_version='1.3',
            table_key=_TABLE_KEY_V13,
            source_anchor=_RELATION_SOURCE_V13,
            status='INCOMPLETE',
            reasons=['DENOMINATOR_NOT_EXPLICIT'],
            denominator_scope_resolved=False,
            denominator_source_anchor=_DENOMINATOR_SOURCE_V13,
            denominator_provenance={
                'resolution_status': 'UNRESOLVED',
                'selected_denominator': None,
            },
            table_source_anchor=_TABLE_SOURCE_V13,
        )
