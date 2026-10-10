"""Adversarial tests for v1.3 denominator provenance and scope resolution."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from researchwitness.jats import parse_jats
from researchwitness.table_arithmetic import check_structured_table_percentages
from researchwitness import denominator_provenance, table_arithmetic
from tools.run_paper_audit_denominator_provenance_v1_3 import (
    _document_identity_accounting,
    _negative_relation_accounting,
    _negative_source_relation_disposition,
)


def _screen(table_markup: str):
    source = (
        '<article><front><article-meta><title-group><article-title>Fixture</article-title>'
        '</title-group></article-meta></front><body><sec>'
        + table_markup
        + '</sec></body></article>'
    ).encode('utf-8')
    return check_structured_table_percentages(parse_jats(source))


def _table(head: str, body: str, *, caption: str = '', footnotes: str = '', table_id: str = 'fixture'):
    caption_markup = f'<caption><title>{caption}</title></caption>' if caption else ''
    return _screen(
        f'<table-wrap id="{table_id}">{caption_markup}<table><thead>{head}</thead>'
        f'<tbody>{body}</tbody></table>{footnotes}</table-wrap>'
    )


def test_many_row_labels_reuse_linear_table_scope_indexes(monkeypatch):
    row_count = 1_000
    body = ''.join(
        f'<tr><th scope="row">Event {index} (n=20)</th><td>1 (5%)</td></tr>'
        for index in range(row_count)
    )
    source = (
        '<article><body><table-wrap id="linear-scope-index"><table><thead><tr>'
        '<th>Outcome</th><th>All participants (N=100)</th></tr></thead><tbody>' + body
        + '</tbody></table></table-wrap></body></article>'
    ).encode('utf-8')
    document = parse_jats(source)

    label_classifier_calls = 0
    context_builds = 0
    original_classifier = denominator_provenance._is_label_only_group_row
    original_builder = table_arithmetic.denominator_table_context

    def counted_classifier(row):
        nonlocal label_classifier_calls
        label_classifier_calls += 1
        return original_classifier(row)

    def counted_builder(table):
        nonlocal context_builds
        context_builds += 1
        return original_builder(table)

    monkeypatch.setattr(denominator_provenance, '_is_label_only_group_row', counted_classifier)
    monkeypatch.setattr(table_arithmetic, 'denominator_table_context', counted_builder)

    result = check_structured_table_percentages(document)

    assert len(result['relations']) == row_count
    assert all(item['status'] == 'ELIGIBLE_CHECKED_MATCH' for item in result['relations'])
    assert context_builds == 1
    assert label_classifier_calls <= 3 * len(document.tables[0].rows)


def test_many_denominator_boundaries_use_preindexed_row_scope(monkeypatch):
    group_count = 400
    body = ''.join(
        f'<tr><th scope="row">Group {index}</th><td>N=20</td></tr>'
        f'<tr><th scope="row">Event {index}</th><td>1 (5%)</td></tr>'
        for index in range(group_count)
    )
    source = (
        '<article><body><table-wrap id="linear-boundary-index"><table><thead><tr>'
        '<th>Outcome</th><th>All participants (N=20)</th></tr></thead><tbody>'
        + body
        + '</tbody></table></table-wrap></body></article>'
    ).encode('utf-8')
    document = parse_jats(source)

    boundary_classifier_calls = 0
    label_classifier_calls = 0
    original_boundary_classifier = denominator_provenance._is_denominator_boundary_row
    original_label_classifier = denominator_provenance._is_label_only_group_row

    def counted_boundary_classifier(row):
        nonlocal boundary_classifier_calls
        boundary_classifier_calls += 1
        return original_boundary_classifier(row)

    def counted_label_classifier(row):
        nonlocal label_classifier_calls
        label_classifier_calls += 1
        return original_label_classifier(row)

    def forbidden_row_lookup(*_args, **_kwargs):
        pytest.fail('per-relation scan of all denominator scope intervals')

    monkeypatch.setattr(
        denominator_provenance, '_is_denominator_boundary_row', counted_boundary_classifier,
    )
    monkeypatch.setattr(
        denominator_provenance, '_is_label_only_group_row', counted_label_classifier,
    )
    monkeypatch.setattr(denominator_provenance, '_active_boundary', forbidden_row_lookup, raising=False)
    monkeypatch.setattr(
        denominator_provenance, '_active_parent_count_groups', forbidden_row_lookup, raising=False,
    )

    result = check_structured_table_percentages(document)

    row_count = len(document.tables[0].rows)
    assert len(result['relations']) == group_count
    assert all(item['status'] == 'ELIGIBLE_CHECKED_MATCH' for item in result['relations'])
    assert boundary_classifier_calls <= row_count
    assert label_classifier_calls <= 2 * row_count


def test_adjacent_denominator_boundaries_keep_their_distinct_bases():
    result = _table(
        '<tr><th>Outcome</th><th>All participants (N=100)</th></tr>',
        '<tr><th scope="row">Group A</th><td>N=20</td></tr>'
        '<tr><th scope="row">Event A</th><td>1 (5%)</td></tr>'
        '<tr><th scope="row">Group B</th><td>N=40</td></tr>'
        '<tr><th scope="row">Event B</th><td>2 (5%)</td></tr>',
        table_id='distinct-adjacent-boundary-bases',
    )

    assert [item['status'] for item in result['relations']] == [
        'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MATCH',
    ]
    assert [item['denominator_exact'] for item in result['relations']] == ['20', '40']


@pytest.mark.parametrize(
    ('status', 'relation_exists', 'operands_exact', 'expected'),
    [
        ('INCOMPLETE', True, True, 'EXACT_OPERAND_ABSTENTION'),
        ('UNSUPPORTED', True, True, 'EXACT_OPERAND_ABSTENTION'),
        ('ELIGIBLE_CHECKED_MATCH', False, False, 'UNMATCHED'),
        ('ELIGIBLE_CHECKED_MATCH', True, False, 'ANCHOR_ONLY_OR_CHANGED_OPERANDS'),
        ('ELIGIBLE_CHECKED_MISMATCH', True, False, 'ANCHOR_ONLY_OR_CHANGED_OPERANDS'),
        ('ELIGIBLE_CHECKED_MATCH', True, True, 'ELIGIBLE_CORRECT_NEGATIVE'),
        ('ELIGIBLE_CHECKED_MISMATCH', True, True, 'EXACT_OPERAND_CHECKED_MISMATCH'),
    ],
    ids=[
        'incomplete-is-abstention', 'unsupported-is-abstention', 'unmatched',
        'anchor-only-match', 'changed-operands-mismatch', 'exact-checked-match',
        'exact-checked-mismatch',
    ],
)
def test_v13_negative_qualification_counts_only_source_confirmed_exact_matches(
    status, relation_exists, operands_exact, expected,
):
    locator = {'arithmetic_correct': True}
    relation = {'status': status} if relation_exists else None

    assert _negative_source_relation_disposition(
        locator, relation, operands_exact,
    ) == expected


def test_v13_negative_qualification_rejects_unconfirmed_source_label():
    assert _negative_source_relation_disposition(
        {'arithmetic_correct': False}, {'status': 'ELIGIBLE_CHECKED_MATCH'}, True,
    ) == 'SOURCE_LABEL_NOT_CONFIRMED'


def test_v13_negative_summary_separates_matches_abstentions_and_unmatched_relations():
    synthetic_rows = [
        ({'arithmetic_correct': True}, {'status': 'INCOMPLETE'}, True),
        ({'arithmetic_correct': True}, {'status': 'UNSUPPORTED'}, True),
        ({'arithmetic_correct': True}, None, False),
        ({'arithmetic_correct': True}, {'status': 'ELIGIBLE_CHECKED_MATCH'}, False),
        ({'arithmetic_correct': True}, {'status': 'ELIGIBLE_CHECKED_MISMATCH'}, False),
        ({'arithmetic_correct': True}, {'status': 'ELIGIBLE_CHECKED_MATCH'}, True),
        ({'arithmetic_correct': True}, {'status': 'ELIGIBLE_CHECKED_MISMATCH'}, True),
    ]
    dispositions = Counter(
        _negative_source_relation_disposition(locator, relation, operands_exact)
        for locator, relation, operands_exact in synthetic_rows
    )
    abstentions = sum(
        relation is not None and relation['status'] in ('INCOMPLETE', 'UNSUPPORTED')
        for _locator, relation, _operands_exact in synthetic_rows
    )

    summary = _negative_relation_accounting(dispositions, abstentions)

    assert summary['source_labelled_correct_relations'] == 7
    assert summary['eligible_correct_source_relations'] == 1
    assert summary['exact_operand_abstentions'] == 2
    assert summary['exact_operand_checked_mismatches'] == 1
    assert summary['source_labelled_abstentions'] == 2
    assert summary['source_anchor_only_or_changed_operand_relations'] == 2
    assert summary['unmatched_source_relations'] == 1


def test_v13_document_accounting_deduplicates_normalized_doi_values():
    records = [
        {'normalized_doi': '10.1234/Repeated'},
        {'normalized_doi': ' 10.1234/repeated '},
        {'normalized_doi': '10.5678/Unique'},
    ]

    assert _document_identity_accounting(records) == {
        'source_records': 3,
        'distinct_normalized_doi_count': 2,
    }


CASES = [
    (
        'global_header_and_local_subgroup',
        '<tr><th>Outcome</th><th>Overall participants (N=100)</th></tr>',
        '<tr><th scope="row">Women</th><td>N=20</td></tr>'
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'multi_level_header',
        '<tr><th>Outcome</th><th>All patients (N=100)</th></tr>'
        '<tr><th></th><th>Women (N=20)</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'treatment_arm_denominator',
        '<tr><th>Outcome</th><th>Placebo arm (N=20)</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'subgroup_row_denominator',
        '<tr><th>Outcome</th><th>All patients (N=100)</th></tr>',
        '<tr><th scope="row">Women</th><td>N=20</td></tr>'
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'same_cell_local_denominator',
        '<tr><th>Outcome</th><th>Overall participants (N=500)</th></tr>',
        '<tr><th scope="row">Event</th><td>44 (20%); n=220</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('220',), None,
    ),
    (
        'row_label_local_denominator',
        '<tr><th>Outcome</th><th>Overall participants (N=100)</th></tr>',
        '<tr><th scope="row">Women (n=20)</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'adjacent_row_local_denominator',
        '<tr><th>Outcome</th><th>Overall participants (N=100)</th></tr>',
        '<tr><th scope="row">Analyzed subgroup</th><td>N=20</td></tr>'
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'repeated_local_denominators_same_source',
        '<tr><th>Outcome</th><th>Women (N=20; n=20)</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'INCOMPLETE', (), 'DENOMINATOR_AMBIGUOUS',
    ),
    (
        'competing_equal_scope_denominators',
        '<tr><th>Outcome</th><th>Women (N=20)</th></tr>'
        '<tr><th></th><th>Women (N=25)</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'INCOMPLETE', (), 'DENOMINATOR_AMBIGUOUS',
    ),
    (
        'denominator_changed_by_footnote',
        '<tr><th>Outcome</th><th>Overall participants (N=20)'
        '<xref ref-type="table-fn" rid="fn1">a</xref></th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'INCOMPLETE', (), 'FOOTNOTE_SCOPE_UNRESOLVED',
    ),
    (
        'explicit_missing_data_category',
        '<tr><th>Characteristic</th><th>Participants (N=50)</th></tr>',
        '<tr><th scope="row">Sex, n (%)</th><td></td></tr>'
        '<tr><th scope="row">Women</th><td>20 (40%)</td></tr>'
        '<tr><th scope="row">Men</th><td>25 (50%)</td></tr>'
        '<tr><th scope="row">Missing</th><td>5</td></tr>',
        'INCOMPLETE', ('50', '50'), 'MISSINGNESS_CHANGES_DENOMINATOR',
    ),
    (
        'available_case_base',
        '<tr><th>Outcome</th><th>Participants (N=20)</th></tr>',
        '<tr><th scope="row">Available cases: Event</th><td>4 (20%)</td></tr>',
        'INCOMPLETE', ('20',), 'MISSINGNESS_CHANGES_DENOMINATOR',
    ),
    (
        'multiple_response_base',
        '<tr><th>Outcome</th><th>Participants (N=100)</th></tr>',
        '<tr><th scope="row">Multiple responses; percentages of responses: Event</th><td>4 (4%)</td></tr>',
        'INCOMPLETE', ('100',), 'MULTIPLE_RESPONSE',
    ),
    (
        'weighted_base',
        '<tr><th>Outcome</th><th>Participants (N=100)</th></tr>',
        '<tr><th scope="row">Weighted event</th><td>4 (4%)</td></tr>',
        'UNSUPPORTED', ('100',), 'WEIGHTED_RESULT',
    ),
    (
        'baseline_vs_follow_up',
        '<tr><th>Outcome</th><th>Baseline patients (N=20)</th>'
        '<th>Follow-up patients (N=10)</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td><td>1 (10%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20', '10'), None,
    ),
    (
        'distinct_week_timepoints',
        '<tr><th>Outcome</th><th>Week 1 patients (N=100)</th>'
        '<th>Week 2 patients (N=50)</th></tr>',
        '<tr><th scope="row">Event</th><td>10 (10%)</td><td>5 (10%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('100', '50'), None,
    ),
    (
        'distinct_analysis_populations',
        '<tr><th>Outcome</th><th>Intention-to-treat population (N=100)</th>'
        '<th>Per-protocol population (N=80)</th></tr>',
        '<tr><th scope="row">Event</th><td>10 (10%)</td><td>8 (10%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('100', '80'), None,
    ),
    (
        'zero_numerator_with_local_denominator',
        '<tr><th>Outcome</th><th>Overall participants (N=100)</th></tr>',
        '<tr><th scope="row">Women</th><td>N=20</td></tr>'
        '<tr><th scope="row">Event</th><td>0 (0%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'numerator_equals_denominator',
        '<tr><th>Outcome</th><th>Women (N=5)</th></tr>',
        '<tr><th scope="row">Event</th><td>5 (100%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('5',), None,
    ),
    (
        'zero_percent',
        '<tr><th>Outcome</th><th>Participants (N=50)</th></tr>',
        '<tr><th scope="row">Event</th><td>0 (0%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('50',), None,
    ),
    (
        'one_hundred_percent',
        '<tr><th>Outcome</th><th>Participants (N=20)</th></tr>',
        '<tr><th scope="row">Event</th><td>20 (100%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'nested_subgroup_headers',
        '<tr><th>Outcome</th><th>All patients (N=100)</th></tr>'
        '<tr><th></th><th>Women (N=20)</th></tr>'
        '<tr><th></th><th>Age under 50 (N=12)</th></tr>',
        '<tr><th scope="row">Event</th><td>3 (25%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('12',), None,
    ),
    (
        'broader_N_and_local_n',
        '<tr><th>Outcome</th><th>Overall patients (N=100)</th></tr>',
        '<tr><th scope="row">Event (n=20)</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'grouped_header_number',
        '<tr><th>Outcome</th><th>Patients (N=1,000)</th></tr>',
        '<tr><th scope="row">Event</th><td>20 (2%)</td></tr>',
        'UNSUPPORTED', (), 'GROUPED_INTEGER_FORMAT_UNSUPPORTED',
    ),
    (
        'duplicated_header_text',
        '<tr><th>Outcome</th><th>Placebo arm (N=20)</th></tr>'
        '<tr><th></th><th>Placebo arm (N=20)</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'INCOMPLETE', (), 'DENOMINATOR_AMBIGUOUS',
    ),
    (
        'body_row_span_is_unsupported',
        '<tr><th>Outcome</th><th>Patients (N=20)</th></tr>',
        '<tr><th scope="row">Event</th><td rowspan="2">4 (20%)</td></tr>'
        '<tr><th scope="row">Other</th></tr>',
        'UNSUPPORTED', ('20',), 'TABLE_STRUCTURE_UNSUPPORTED',
    ),
    (
        'table_global_N_and_row_specific_n',
        '<tr><th>Outcome</th><th>Group</th></tr>',
        '<tr><th scope="row">Event (n=20)</th><td>4 (20%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20',), None,
    ),
    (
        'same_subgroup_across_timepoints',
        '<tr><th>Outcome</th><th>Baseline</th><th>Follow-up</th></tr>'
        '<tr><th></th><th>Women (N=20)</th><th>Women (N=10)</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td><td>1 (10%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20', '10'), None,
    ),
    (
        'same_group_different_analysis_sets',
        '<tr><th>Outcome</th><th>Intention-to-treat women (N=20)</th>'
        '<th>Per-protocol women (N=10)</th></tr>',
        '<tr><th scope="row">Event</th><td>2 (10%)</td><td>4 (40%)</td></tr>',
        'ELIGIBLE_CHECKED_MATCH', ('20', '10'), None,
    ),
    (
        'absent_denominator_fails_closed',
        '<tr><th>Outcome</th><th>Participants</th></tr>',
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        'INCOMPLETE', (), 'DENOMINATOR_NOT_EXPLICIT',
    ),
]


@pytest.mark.parametrize(
    ('case_name', 'head', 'body', 'expected_status', 'expected_denominators', 'expected_reason'),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_v1_3_adversarial_denominator_resolution(
    case_name,
    head,
    body,
    expected_status,
    expected_denominators,
    expected_reason,
):
    footnotes = (
        '<table-wrap-foot><fn id="fn1"><label>a</label>'
        '<p>Marker a applies to participants with complete records.</p></fn></table-wrap-foot>'
        if case_name == 'denominator_changed_by_footnote' else ''
    )
    result = _table(head, body, footnotes=footnotes, table_id=case_name)
    relations = result['relations']
    assert relations, case_name
    assert all(item['status'] == expected_status for item in relations), case_name
    if expected_denominators:
        assert len(relations) == len(expected_denominators), case_name
        for item, expected_denominator in zip(relations, expected_denominators):
            assert item['denominator_scope_resolved'] is True
            selected = item['denominator_provenance']['selected_denominator']
            assert selected is not None
            assert selected['value_exact'] == expected_denominator
            assert selected['source_anchor']['element_path']
            if item['status'] in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH'):
                assert item['denominator_exact'] == expected_denominator
    else:
        assert all(item['denominator_scope_resolved'] is False for item in relations), case_name
    if expected_reason:
        assert all(item['primary_skip_reason'] == expected_reason for item in relations), case_name
    for item in relations:
        if item['status'] in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH'):
            assert item['denominator_scope_resolved'] is True
            assert item['denominator_provenance']['resolution_status'] == 'RESOLVED'
        if item['primary_skip_reason'] == 'DENOMINATOR_AMBIGUOUS':
            candidates = item['denominator_provenance']['rejected_competing_denominators']
            assert len(candidates) >= 2
            assert all(candidate['rejection_reasons'] == ['DENOMINATOR_AMBIGUOUS'] for candidate in candidates)


@pytest.mark.parametrize(
    'heading',
    [
        'Primary outcome',
        'Primary efficacy endpoint',
        'Primary safety outcome',
        'Major secondary outcome',
        'Primary outcome measures',
        'Primary endpoint measures',
        'Primary end point measures',
    ],
)
def test_qualified_outcome_headings_preserve_the_prior_subgroup_scope(heading):
    result = _table(
        '<tr><th>Outcome</th><th>Participants (N=100)</th></tr>',
        '<tr><th scope="row">Women (N=20)</th><td></td></tr>'
        f'<tr><th scope="row">{heading}</th><td></td></tr>'
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        table_id='transparent-outcome-heading',
    )

    relation = result['relations'][0]

    assert relation['status'] == 'ELIGIBLE_CHECKED_MATCH'
    assert relation['denominator_exact'] == '20'


def test_unclassified_label_only_heading_blocks_a_broader_denominator():
    result = _table(
        '<tr><th>Outcome</th><th>Participants (N=100)</th></tr>',
        '<tr><th scope="row">Clinical history</th><td></td></tr>'
        '<tr><th scope="row">Event</th><td>20 (20%)</td></tr>',
        table_id='unclassified-scope-heading',
    )

    relation = result['relations'][0]

    assert relation['status'] == 'INCOMPLETE'
    assert relation['primary_skip_reason'] == 'DENOMINATOR_NOT_EXPLICIT'
    assert relation['denominator_scope_resolved'] is False
    assert relation['denominator_provenance']['selected_denominator'] is None


@pytest.mark.parametrize(
    ('header', 'reason'),
    [
        ('Participants (N=9999999999)', 'MALFORMED_NUMERIC_TOKEN'),
        ('Participants (N=-10)', 'OPERANDS_OUTSIDE_PROPORTION_DOMAIN'),
        ('Participants (N=10.5)', 'MALFORMED_NUMERIC_TOKEN'),
        ('Participants (N=１０)', 'MALFORMED_NUMERIC_TOKEN'),
        ('Participants (N=1\u202f000)', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'),
        ('Participants (N=1e3)', 'MALFORMED_NUMERIC_TOKEN'),
    ],
)
def test_malformed_or_pathological_denominators_fail_closed(header, reason):
    result = _table(
        f'<tr><th>Outcome</th><th>{header}</th></tr>',
        '<tr><th scope="row">Event</th><td>1 (1%)</td></tr>',
        table_id='pathological-denominator',
    )
    relation = result['relations'][0]
    assert relation['status'] in ('INCOMPLETE', 'UNSUPPORTED')
    assert relation['primary_skip_reason'] == reason
    assert relation['denominator_scope_resolved'] is False
    assert relation['denominator_provenance']['selected_denominator'] is None


def test_same_cell_n_is_selected_before_zero_percent_arithmetic():
    result = _table(
        '<tr><th>Outcome</th><th>All participants (N=100)</th></tr>',
        '<tr><th scope="row">Event</th><td>0 (0%); N=20</td></tr>',
        table_id='zero-numerator-same-cell',
    )
    relation = result['relations'][0]
    assert relation['status'] == 'ELIGIBLE_CHECKED_MATCH'
    assert relation['denominator_exact'] == '20'
    assert relation['denominator_provenance']['selected_denominator']['provenance_class'] == 'CELL_LOCAL_EXPLICIT'
    assert any(
        item['value_exact'] == '100'
        and item['rejection_reasons'] == ['BROADER_SCOPE_THAN_SELECTED']
        for item in relation['denominator_provenance']['rejected_competing_denominators']
    )


@pytest.mark.parametrize(
    ('percent_context', 'expected_denominator'),
    [
        ('<tr><th></th><th>No. (%)</th></tr>', '10'),
        ('<tr><th></th><th>Percentage (%)</th></tr>', '10'),
    ],
)
def test_explicit_percent_header_allows_unmarked_displayed_percent(percent_context, expected_denominator):
    result = _table(
        '<tr><th>Outcome</th><th>Participants (N=10)</th></tr>' + percent_context,
        '<tr><th scope="row">Event</th><td>1 (10)</td></tr>',
        table_id='explicit-percent-header',
    )
    relation = result['relations'][0]
    assert relation['status'] == 'ELIGIBLE_CHECKED_MATCH'
    assert relation['denominator_exact'] == expected_denominator
    assert relation['denominator_scope_resolved'] is True


def test_explicit_percent_row_label_allows_unmarked_displayed_percent():
    result = _table(
        '<tr><th>Outcome</th><th>Participants (N=10)</th></tr>',
        '<tr><th scope="row">Event, %</th><td>1 (10)</td></tr>',
        table_id='explicit-percent-row-label',
    )
    relation = result['relations'][0]
    assert relation['status'] == 'ELIGIBLE_CHECKED_MATCH'
    assert relation['denominator_exact'] == '10'


def test_unmarked_numeric_pair_without_percent_unit_evidence_fails_closed():
    result = _table(
        '<tr><th>Outcome</th><th>Participants (N=10)</th></tr>',
        '<tr><th scope="row">Event</th><td>1 (10)</td></tr>',
        table_id='implicit-percent-unit',
    )
    relation = result['relations'][0]
    assert relation['status'] == 'INCOMPLETE'
    assert relation['primary_skip_reason'] == 'PERCENT_UNIT_NOT_EXPLICIT'
    assert relation['denominator_scope_resolved'] is True
    assert relation.get('denominator_exact') is None


def test_row_n_applies_to_aggregate_column_while_stratified_columns_use_their_bases():
    result = _table(
        '<tr><th>Assessment</th><th>All studies (n=318)</th>'
        '<th>Older studies (n=167)</th><th>Recent studies (n=151)</th></tr>',
        '<tr><th scope="row">Bayesian framework only (n=214)</th>'
        '<td>35 (16%)</td><td>24 (14%)</td><td>11 (7%)</td></tr>',
        table_id='row-n-aggregate-versus-stratified-columns',
    )
    relations = result['relations']
    assert [item['status'] for item in relations] == [
        'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MATCH',
    ]
    assert [item['denominator_exact'] for item in relations] == ['214', '167', '151']
    selected = [item['denominator_provenance']['selected_denominator'] for item in relations]
    assert [item['provenance_class'] for item in selected] == [
        'ROW_LOCAL_EXPLICIT', 'COLUMN_HEADER_EXPLICIT', 'COLUMN_HEADER_EXPLICIT',
    ]
    for relation in relations[1:]:
        row_base = next(
            item for item in relation['denominator_provenance']['rejected_competing_denominators']
            if item['raw_value'] == '214'
        )
        assert row_base['rejection_reasons'] == ['NOT_STRUCTURALLY_APPLICABLE']


def test_incomplete_category_block_does_not_reconstruct_a_missingness_denominator():
    result = _table(
        '<tr><th>Characteristic</th><th>Participants (N=20)</th></tr>',
        '<tr><th scope="row">Income</th><td></td></tr>'
        '<tr><th scope="row">Lower</th><td>5 (50%)</td></tr>'
        '<tr><th scope="row">Middle</th><td>3 (30%)</td></tr>'
        '<tr><th scope="row">Upper</th><td>2 (20%)</td></tr>',
        table_id='category-block-available-case-base',
    )
    assert len(result['relations']) == 3
    for relation in result['relations']:
        assert relation['status'] == 'INCOMPLETE'
        assert relation['primary_skip_reason'] == 'MISSINGNESS_CHANGES_DENOMINATOR'
        assert relation['denominator_scope_resolved'] is False
        assert relation.get('denominator_exact') is None
        provenance = relation['denominator_provenance']
        assert provenance['resolution_status'] == 'UNRESOLVED'
        assert provenance['selected_denominator'] is None
        assert any(
            candidate['raw_value'] == '20'
            and candidate['rejection_reasons'] == ['MISSINGNESS_CHANGES_DENOMINATOR']
            for candidate in provenance['rejected_competing_denominators']
        )


def test_one_cell_error_in_a_category_block_is_not_silenced_as_missingness():
    result = _table(
        '<tr><th>Characteristic</th><th>Participants (N=20)</th></tr>',
        '<tr><th scope="row">PCP group</th><td></td></tr>'
        '<tr><th scope="row">North</th><td>8 (40%)</td></tr>'
        '<tr><th scope="row">South</th><td>5 (25%)</td></tr>'
        '<tr><th scope="row">Employed</th><td>4 (35%)</td></tr>',
        table_id='category-block-single-arithmetic-error',
    )
    assert [item['status'] for item in result['relations']] == [
        'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH',
    ]
    candidate = result['findings'][0]
    assert candidate['row_identity'] == 'Employed'
    assert candidate['denominator_exact'] == '20'


def test_counted_unknown_category_is_not_treated_as_missing_data():
    result = _table(
        '<tr><th>Characteristic</th><th>Participants (N=20)</th></tr>',
        '<tr><th scope="row">Race</th><td></td></tr>'
        '<tr><th scope="row">White</th><td>15 (75%)</td></tr>'
        '<tr><th scope="row">Unknown</th><td>5 (25%)</td></tr>',
        table_id='counted-unknown-category',
    )
    assert [item['status'] for item in result['relations']] == [
        'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MATCH',
    ]
    assert all(item['primary_skip_reason'] is None for item in result['relations'])


def test_candidate_limit_and_extreme_header_depth_are_bounded():
    header_rows = ['<tr><th>Outcome</th><th>Participants (N=20)</th></tr>']
    header_rows.extend('<tr><th></th><th>Participants (N=20)</th></tr>' for _ in range(64))
    result = _table(
        ''.join(header_rows),
        '<tr><th scope="row">Event</th><td>4 (20%)</td></tr>',
        table_id='bounded-header-depth',
    )
    relation = result['relations'][0]
    assert relation['status'] == 'INCOMPLETE'
    assert relation['primary_skip_reason'] == 'DENOMINATOR_CANDIDATE_LIMIT'
    assert relation['denominator_scope_resolved'] is False


def test_v1_2_failure_fixtures_are_hash_bound_to_the_full_v1_3_replay():
    root = Path(__file__).resolve().parents[1]
    validation = root / 'validation/paper-audit-denominator-provenance'
    replay_path = validation / 'DEVELOPMENT_NEGATIVE_REPLAY_V1_3.json'
    fixture_path = validation / 'DEVELOPMENT_V1_2_DENOMINATOR_PROVENANCE_FIXTURES_V1_3.json'
    plan_path = validation / 'QUALIFICATION_PLAN_V1_3.md'
    replay_bytes = replay_path.read_bytes()
    replay_sha256 = hashlib.sha256(replay_bytes).hexdigest()
    replay = json.loads(replay_bytes)
    fixtures = json.loads(fixture_path.read_text(encoding='utf-8'))

    assert fixtures['reserved_records_included'] is False
    assert fixtures['v1_3_contract_version'] == '1.3'
    assert fixtures['provenance']['qualification_plan_sha256'] == hashlib.sha256(
        plan_path.read_bytes()
    ).hexdigest()
    assert fixtures['provenance']['v1_3_negative_replay_artifact_sha256'] == replay_sha256
    assert replay['reserved_records_included'] is False
    assert replay['detector_executed_on_reserved_records'] is False

    ledger_by_key = {}
    for item in replay['relation_ledger']:
        key = (item['source_id'], item['source_sha256'], item['contract_id'], item['source_cell_path'])
        ledger_by_key.setdefault(key, []).append(item)
    assert len(replay['relation_ledger']) == 4163
    assert len(fixtures['fixtures']) == 16
    assert fixtures['summary']['denominator_scope_false_candidates'] == 14
    assert fixtures['summary']['zero_numerator_wrong_denominator_matches'] == 2

    fixture_ids = set()
    for fixture in fixtures['fixtures']:
        fixture_ids.add(fixture['fixture_id'])
        source = fixture['source']
        source_relation = fixture['source_relation']
        observation = fixture['v1_3_observation']
        expected = fixture['expected_v1_3_outcome']
        key = (
            source['source_id'], source['sha256'], source_relation['contract_id'],
            source_relation['cell_path'],
        )
        matching_rows = [
            item for item in ledger_by_key[key]
            if item['source_operands'] == {
                'numerator_exact': str(source_relation['numerator']),
                'denominator_exact': str(source_relation['correct_local_denominator']),
                'reported_percent': str(source_relation['reported_percent']),
                'display_precision': source_relation['display_precision_digits'],
                'arithmetic_correct': source_relation['arithmetic_correct_in_locked_source_manifest'],
            }
        ]
        assert len(matching_rows) == 1
        replay_relation = matching_rows[0]
        actual_provenance = replay_relation['denominator_provenance']

        assert source['manifest_split_status'] == 'DEVELOPMENT'
        assert observation['negative_replay_artifact_sha256'] == replay_sha256
        assert observation['contract_version'] == '1.3'
        assert observation['report_relation_id'] == replay_relation['report_relation_id']
        assert observation['join_level'] == replay_relation['join_level']
        assert observation['report_relation_status'] == replay_relation['report_relation_status']
        assert observation['primary_skip_reason'] == replay_relation['primary_skip_reason']
        assert observation['candidate_emitted'] is replay_relation['candidate_emitted'] is False
        assert observation['report_operands'] == replay_relation['report_operands']
        assert observation['denominator_scope_resolved'] is replay_relation['denominator_scope_resolved']
        assert observation['denominator_resolution_status'] == actual_provenance['resolution_status']
        assert observation['denominator_resolution_reason'] == actual_provenance['resolution_reason']

        observed_selected = observation['selected_denominator']
        actual_selected = actual_provenance['selected_denominator']
        if observed_selected is None:
            assert actual_selected is None
        else:
            assert actual_selected is not None
            for field in ('value_exact', 'provenance_class', 'source_anchor'):
                assert observed_selected[field] == actual_selected[field]

        observed_rejected = observation['rejected_competing_denominators']
        actual_rejected = actual_provenance['rejected_competing_denominators']
        summarize = lambda item: {
            'value_exact': item['value_exact'],
            'provenance_class': item['provenance_class'],
            'rejection_reasons': item['rejection_reasons'],
            'source_anchor': item['source_anchor'],
        }
        assert [summarize(item) for item in observed_rejected] == [
            summarize(item) for item in actual_rejected
        ]

        required_result = expected['required_result']
        if required_result == 'NO_FALSE_CANDIDATE_SOURCE_VALID_MATCH':
            assert replay_relation['report_relation_status'] == 'ELIGIBLE_CHECKED_MATCH'
            assert actual_selected['value_exact'] == expected['correct_selected_denominator']
            assert source_relation['arithmetic_correct_in_locked_source_manifest'] is True
        elif required_result == 'ELIGIBLE_CHECKED_MATCH_AFTER_LOCAL_DENOMINATOR_RESOLUTION':
            assert replay_relation['report_relation_status'] == 'ELIGIBLE_CHECKED_MATCH'
            assert source_relation['numerator'] == '0'
            assert actual_selected['value_exact'] == expected['selected_denominator']
            assert any(
                item['value_exact'] == expected['rejected_broad_denominator']
                and expected['rejected_broad_denominator_reason'] in item['rejection_reasons']
                for item in actual_rejected
            )
            assert expected['zero_arithmetic_coincidence_validated_wrong_denominator'] is False
        elif required_result == 'INCOMPLETE_MISSINGNESS_CHANGES_DENOMINATOR_NO_CANDIDATE':
            assert replay_relation['report_relation_status'] == 'INCOMPLETE'
            assert replay_relation['primary_skip_reason'] == 'MISSINGNESS_CHANGES_DENOMINATOR'
            assert actual_selected is None
            assert replay_relation['report_operands']['denominator_exact'] is None
        else:
            pytest.fail(f'unknown v1.3 failure fixture expectation: {required_result}')

    assert len(fixture_ids) == 16


def test_positive_replay_preserves_denominator_provenance_for_every_checked_relation():
    root = Path(__file__).resolve().parents[1]
    replay = json.loads(
        (root / 'validation/paper-audit-denominator-provenance/DEVELOPMENT_POSITIVE_REPLAY_V1_3.json')
        .read_text(encoding='utf-8')
    )
    assert replay['reserved_records_included'] is False
    assert replay['detector_executed_on_reserved_records'] is False
    reports = {item['case_id']: item for item in replay['reports']}
    ledger = replay['checked_relationship_provenance']
    expected_count = sum(
        report['relation_status_counts'].get(status, 0)
        for report in reports.values()
        for status in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH')
    )
    assert replay['summary']['checked_relationships_with_full_denominator_provenance'] == expected_count
    assert replay['summary']['checked_relationship_provenance_complete'] is True
    assert len(ledger) == expected_count
    relation_ids = [item['relation_id'] for item in ledger]
    assert len(relation_ids) == len(set(relation_ids))

    for item in ledger:
        assert item['contract_version'] == '1.3'
        assert item['status'] in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH')
        report = reports[item['case_id']]
        assert item['source_sha256'] == report['source_sha256']
        assert item['report_sha256'] == report['report_sha256']
        assert item['denominator_scope_resolved'] is True
        provenance = item['denominator_provenance']
        selected = provenance['selected_denominator']
        assert provenance['resolution_status'] == 'RESOLVED'
        assert selected['value_exact'] == item['denominator_exact']
        assert selected['source_anchor'] == item['denominator_source_anchor']
        assert selected['source_anchor']['source_sha256'] == item['source_sha256']
        assert all(
            candidate['rejection_reasons']
            for candidate in provenance['rejected_competing_denominators']
        )


@pytest.mark.parametrize(
    ('header', 'reason'),
    [
        ('Participants (N=1\u00a0000)', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'),
        ('Participants (N=1,000)', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'),
    ],
)
def test_nonbreaking_and_grouped_numeric_denominators_fail_closed(header, reason):
    result = _table(
        f'<tr><th>Outcome</th><th>{header}</th></tr>',
        '<tr><th scope="row">Event</th><td>1 (0%)</td></tr>',
        table_id='grouped-numeric-denominator',
    )
    relation = result['relations'][0]
    assert relation['status'] == 'UNSUPPORTED'
    assert relation['primary_skip_reason'] == reason
    assert relation['denominator_scope_resolved'] is False
    assert relation['denominator_provenance']['selected_denominator'] is None


def test_malformed_span_and_pathological_footnote_xrefs_fail_closed():
    malformed_span = _table(
        '<tr><th>Outcome</th><th>Participants (N=20)</th></tr>',
        '<tr><th scope="row">Event</th><td rowspan="not-an-integer">1 (5%)</td></tr>',
        table_id='malformed-span',
    )['relations'][0]
    assert malformed_span['status'] == 'UNSUPPORTED'
    assert malformed_span['primary_skip_reason'] == 'TABLE_STRUCTURE_UNSUPPORTED'

    xrefs = ''.join('<xref ref-type="table-fn" rid="fn1">a</xref>' for _ in range(128))
    footnote_markup = (
        '<table-wrap-foot><fn id="fn1"><label>a</label>'
        '<p>Participants N=20.</p></fn></table-wrap-foot>'
    )
    with_xrefs = _table(
        f'<tr><th>Outcome</th><th>Participants (N=20){xrefs}</th></tr>',
        '<tr><th scope="row">Event</th><td>1 (5%)</td></tr>',
        footnotes=footnote_markup,
        table_id='pathological-footnote-xrefs',
    )['relations'][0]
    assert with_xrefs['status'] == 'UNSUPPORTED'
    assert with_xrefs['primary_skip_reason'] == 'FOOTNOTE_SCOPE_UNRESOLVED'
    assert with_xrefs['denominator_scope_resolved'] is False
    assert with_xrefs['denominator_provenance']['selected_denominator'] is None


def test_duplicate_table_ids_keep_source_relation_ids_unique():
    markup = ''.join(
        '<table-wrap id="duplicate"><table><thead><tr><th>Outcome</th>'
        '<th>Participants (N=10)</th></tr></thead><tbody><tr><th scope="row">Event</th>'
        '<td>1 (10%)</td></tr></tbody></table></table-wrap>'
        for _ in range(2)
    )
    result = _screen(markup)
    relation_ids = [item['relation_id'] for item in result['relations']]
    assert len(relation_ids) == 2
    assert len(set(relation_ids)) == 2
    assert all(item['status'] == 'ELIGIBLE_CHECKED_MATCH' for item in result['relations'])


def test_malicious_markup_in_row_label_is_inert_and_escaped_in_report(tmp_path):
    from researchwitness.paper_audit import run_paper_audit

    source = tmp_path / 'hostile-label.xml'
    source.write_text(
        '<article><front><article-meta><title-group><article-title>Fixture</article-title>'
        '</title-group></article-meta></front><body><sec><table-wrap><table><thead>'
        '<tr><th>Outcome</th><th>Participants (N=100)</th></tr></thead><tbody>'
        '<tr><th scope="row">&lt;script&gt;alert(1)&lt;/script&gt;</th><td>1 (2%)</td></tr>'
        '</tbody></table></table-wrap></sec></body></article>',
        encoding='utf-8',
    )
    output = tmp_path / 'hostile-output'
    run_paper_audit(source, output)
    html = (output / 'report.html').read_text(encoding='utf-8')
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
