"""Synthetic Table resolver cases adapted from PR #11; no audit stack."""
import pytest
from dataclasses import replace

from researchwitness.denominator_provenance import (
    parent_count_groups, resolve_denominator, subgroup_boundaries,
)
from researchwitness.jats_table_projection import project_jats_tables

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
    ("name", "head", "body", "old_status", "denominators", "reason"), CASES,
    ids=[case[0] for case in CASES],
)
def test_table_resolution(name, head, body, old_status, denominators, reason):
    footnotes = (
        '<table-wrap-foot><fn id="fn1"><label>a</label>'
        '<p>Marker a applies to participants with complete records.</p></fn></table-wrap-foot>'
        if name == "denominator_changed_by_footnote" else ""
    )
    source = ("<article><body><table-wrap><table><thead>" + head
              + "</thead><tbody>" + body
              + "</tbody></table>" + footnotes + "</table-wrap></body></article>").encode()
    table = project_jats_tables(source).tables[0]
    table = replace(table, rows=tuple(
        replace(row, row_group=row.row_group.split(":", 1)[0]) for row in table.rows
    ))
    boundaries, groups = subgroup_boundaries(table), parent_count_groups(table)
    results = [
        resolve_denominator(table, row, cell, i, boundaries, groups)
        for i, row in enumerate(table.rows) for cell in row.cells
        if "%" in cell.raw_text and "(" in cell.raw_text
        and row.row_group == "tbody" and cell.column_start > 0
    ]
    assert results
    if denominators:
        assert [str(item["denominator_exact"]) for item in results] == list(denominators)
    else:
        assert all(not item["denominator_scope_resolved"] for item in results)
    for item in results:
        provenance = item["denominator_provenance"]
        if item["denominator_scope_resolved"]:
            assert provenance["selected_denominator"]["source_anchor"]["element_path"]
        assert all(candidate["rejection_reasons"]
                   for candidate in provenance["rejected_competing_denominators"])
