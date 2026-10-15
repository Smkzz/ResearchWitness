"""Synthetic regression and adversarial tests for the offline JATS table aid."""
from __future__ import annotations

import hashlib
import unittest

from tools.jats_percentage_audit import (
    JATSSourceError,
    audit_jats_percentage_tables,
)


def jats(body: str) -> bytes:
    return f"<article><body>{body}</body></article>".encode("utf-8")


class JATSPercAuditTests(unittest.TestCase):
    def test_inherits_one_explicit_table_denominator_and_returns_byte_evidence(self):
        data = jats(
            '<table-wrap id="synthetic-table">'
            '<label>Table 1</label>'
            '<caption><p>Participants in the analysis set (N=50).</p></caption>'
            '<table><thead><tr><th>Reason</th><th>Patients, n (%)</th></tr></thead>'
            '<tbody><tr><td>Reason A</td><td>4 (8.00)</td></tr>'
            '<tr><td>Reason B</td><td>4 (8.10)</td></tr></tbody></table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        self.assertEqual(report["source_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(report["tables_inspected"], 1)
        self.assertEqual(
            [item["status"] for item in report["results"]],
            ["arithmetic_match", "arithmetic_mismatch_candidate"],
        )
        mismatch = report["results"][1]
        self.assertEqual(mismatch["numerator"], 4)
        self.assertEqual(mismatch["denominator"], 50)
        self.assertEqual(mismatch["reported_percent"], "8.10")
        self.assertEqual(mismatch["contract_expected_percent"], "8.00")
        self.assertEqual(mismatch["denominator_scope"], "table_caption_or_footnote")
        evidence = mismatch["evidence"]
        self.assertEqual(evidence["table_id"], "synthetic-table")
        self.assertEqual(evidence["row_index"], 2)
        self.assertEqual(evidence["cell_index"], 2)
        self.assertEqual(data[evidence["byte_start"]:evidence["byte_end"]], b"<td>4 (8.10)</td>")
        denominator = evidence["denominator_sources"][0]["evidence"]
        self.assertEqual(denominator["role"], "table_caption")
        self.assertIn("N=50", denominator["quote"])

    def test_maps_colspan_group_header_and_per_column_denominators(self):
        data = jats(
            '<table-wrap id="groups"><table>'
            '<thead><tr><th></th><th colspan="2">Group A (N=50)</th>'
            '<th colspan="2">Group B (N=40)</th></tr>'
            '<tr><th>Reason</th><th>Patients n (%)</th><th>Other n (%)</th>'
            '<th>Patients n (%)</th><th>Other n (%)</th></tr></thead>'
            '<tbody><tr><td>Reason A</td><td>2 (4.00)</td><td>1 (2.00)</td>'
            '<td>2 (5.00)</td><td>1 (2.50)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        self.assertEqual(
            [(item["denominator"], item["status"]) for item in report["results"]],
            [(50, "arithmetic_match"), (50, "arithmetic_match"),
             (40, "arithmetic_match"), (40, "arithmetic_match")],
        )
        self.assertEqual(
            [item["denominator_scope"] for item in report["results"]],
            ["column_header"] * 4,
        )

    def test_reads_grouped_counts_and_denominators_without_truncating_at_commas(self):
        data = jats(
            '<table-wrap><caption><p>Analysis set N=304,997.</p></caption><table>'
            '<thead><tr><th>Reason</th><th>n (%)</th></tr></thead><tbody>'
            '<tr><td>Reason A</td><td>7,362 (2.4)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "arithmetic_match")
        self.assertEqual(result["numerator"], 7362)
        self.assertEqual(result["denominator"], 304997)
        self.assertEqual(result["exact_ratio_percent"], "736200/304997")

    def test_zero_counts_keep_comma_grouped_column_denominators(self):
        data = jats(
            '<table-wrap><table><thead><tr><th></th>'
            '<th colspan="1">North site (N=205,488), n (%)</th>'
            '<th colspan="1">South site (N=304,997), n (%)</th></tr></thead><tbody>'
            '<tr><td>Outcome absent</td><td>0 (0.0)</td><td>0 (0.00)</td></tr>'
            '</tbody></table></table-wrap>'
        )
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual([(r["numerator"], r["denominator"], r["status"]) for r in results], [
            (0, 205488, "arithmetic_match"), (0, 304997, "arithmetic_match"),
        ])
        self.assertEqual([r["exact_ratio_percent"] for r in results], ["0/205488", "0/304997"])

    def test_article_group_size_is_conditional_and_source_anchored(self):
        data = jats(
            '<p>Participants were assigned to the control group (n=48) and '
            'the intervention group (n=41).</p>'
            '<table-wrap><caption><p>Answer distribution in Interventional Group</p></caption>'
            '<table><thead><tr><th>Outcome</th><th>n (%)</th></tr></thead><tbody>'
            '<tr><td>Correct</td><td>38 (85.4%)</td></tr>'
            '<tr><td>Incorrect</td><td>3 (14.6%)</td></tr>'
            '</tbody></table></table-wrap>'
        )
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual([r["status"] for r in results], ["scope_ambiguous", "scope_ambiguous"])
        self.assertEqual([r["denominator"] for r in results], [None, None])
        self.assertEqual([r["conditional_calculation"]["denominator"] for r in results], [41, 41])
        self.assertEqual([r["conditional_calculation"]["rounded_percent"] for r in results], ["92.7", "7.3"])
        self.assertTrue(all(not r["conditional_calculation"]["arithmetic_matches"] for r in results))
        first = results[0]["conditional_calculation"]["evidence"]
        for anchor in (first["group_population"], first["table_population_context"]):
            source = data[anchor["byte_start"]:anchor["byte_end"]]
            self.assertTrue(source.startswith(b"<p>") or source.startswith(b"<caption>"))
            self.assertIn(anchor["quote"].encode(), source)

    def test_article_group_size_does_not_cross_groups_or_conflicting_values(self):
        unrelated = jats(
            '<p>Control group (n=48); intervention group (n=41).</p>'
            '<table-wrap><caption><p>Comparator group outcomes</p></caption><table>'
            '<thead><tr><th>Outcome</th><th>n (%)</th></tr></thead><tbody>'
            '<tr><td>Response</td><td>8 (16.7%)</td></tr></tbody></table></table-wrap>'
        )
        unrelated_result = audit_jats_percentage_tables(unrelated)["results"][0]
        self.assertIsNone(unrelated_result.get("conditional_calculation"))
        self.assertIsNone(unrelated_result["denominator"])

        conflicting = jats(
            '<p>Intervention group (n=41) at enrollment.</p>'
            '<p>Intervention group (n=39) completed follow-up.</p>'
            '<table-wrap><caption><p>Intervention Group outcomes</p></caption><table>'
            '<thead><tr><th>Outcome</th><th>n (%)</th></tr></thead><tbody>'
            '<tr><td>Response</td><td>38 (85.4%)</td></tr></tbody></table></table-wrap>'
        )
        conflicting_result = audit_jats_percentage_tables(conflicting)["results"][0]
        self.assertIsNone(conflicting_result.get("conditional_calculation"))
        self.assertEqual(
            [item["value"] for item in conflicting_result["evidence"]["article_group_population_conflicts"]],
            [41, 39],
        )

    def test_article_group_population_scan_fails_closed_at_its_limit(self):
        statements = "".join("<p>Intervention group (n=41).</p>" for _ in range(65))
        data = jats(
            statements
            + '<table-wrap><caption><p>Intervention Group outcomes</p></caption><table>'
            + '<thead><tr><th>Outcome</th><th>n (%)</th></tr></thead><tbody>'
            + '<tr><td>Response</td><td>38 (85.4%)</td></tr></tbody>'
            + '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertIsNone(result.get("conditional_calculation"))
        self.assertIsNone(result["denominator"])
        self.assertEqual(result["status"], "scope_ambiguous")

    def test_uses_explicit_n_over_n_ratio_in_a_cell(self):
        data = jats(
            '<table-wrap><caption><p>Population N=120.</p></caption><table>'
            '<thead><tr><th>Characteristic</th><th>n/N (%)</th></tr></thead><tbody>'
            '<tr><td>Female</td><td>1,100/2,000 (54.9%) #</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "arithmetic_mismatch_candidate")
        self.assertEqual(result["numerator"], 1100)
        self.assertEqual(result["denominator"], 2000)
        self.assertEqual(result["denominator_scope"], "cell_ratio")
        self.assertEqual(result["contract_expected_percent"], "55.0")
        denominator = result["evidence"]["denominator_sources"][-1]
        self.assertEqual(denominator["value"], 2000)
        self.assertEqual(denominator["evidence"]["role"], "cell_ratio_denominator")
        self.assertEqual(
            data[denominator["evidence"]["byte_start"]:denominator["evidence"]["byte_end"]],
            b"<td>1,100/2,000 (54.9%) #</td>",
        )

    def test_rejects_malformed_thousands_grouping_in_count_and_denominator(self):
        data = jats(
            '<table-wrap><caption><p>Analysis set N=304,99.</p></caption><table>'
            '<thead><tr><th>Reason</th><th>n (%)</th></tr></thead><tbody>'
            '<tr><td>Reason A</td><td>7,362 (2.4)</td></tr>'
            '<tr><td>Reason B</td><td>7,36 (2.4)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        self.assertEqual(len(report["results"]), 1)
        self.assertEqual(report["results"][0]["reason"], "no_explicit_denominator")
        self.assertEqual(report["results"][0]["numerator"], 7362)

    def test_abstains_when_row_group_marks_per_row_n_over_n_denominators(self):
        data = jats(
            '<table-wrap><caption><p>Analysis set (N=100).</p></caption><table><tbody>'
            '<tr><td>Parameter</td><td>Value (n)</td></tr>'
            '<tr><td>Age groups; n (% n/N)</td><td></td></tr>'
            '<tr><td>Group A</td><td>25 (25.0)</td></tr>'
            '</tbody></table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        self.assertEqual(len(report["results"]), 1)
        result = report["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "row_specific_denominator_not_reported")
        self.assertIsNone(result["denominator"])
        self.assertIn("n (% n/N)", result["evidence"]["row_group_context"]["quote"])

    def test_uses_an_explicit_per_row_denominator_column(self):
        data = jats(
            '<table-wrap><caption><p>Study population N=100.</p></caption><table>'
            '<thead><tr><th>Category</th><th>n</th><th>N</th><th>%</th></tr></thead>'
            '<tbody><tr><td colspan="4">Outcomes, n (% n/N)</td></tr>'
            '<tr><td>Group A</td><td>2</td><td>40</td><td>5.00</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "arithmetic_match")
        self.assertEqual(result["numerator"], 2)
        self.assertEqual(result["denominator"], 40)
        self.assertEqual(result["denominator_scope"], "row_denominator_column")
        denominator_source = result["evidence"]["denominator_sources"][-1]["evidence"]
        self.assertEqual(denominator_source["role"], "row_denominator_cell")
        self.assertEqual(
            data[denominator_source["byte_start"]:denominator_source["byte_end"]],
            b"<td>40</td>",
        )

    def test_inherits_global_denominator_for_explicit_n_percent_group(self):
        data = jats(
            '<table-wrap><caption><p>All categories use the analysis set (N=100).</p></caption>'
            '<table><tbody><tr><td>Parameter</td><td>Value</td></tr>'
            '<tr><td>Age groups; n (%)</td><td></td></tr>'
            '<tr><td>Group A</td><td>25 (25.0)</td></tr></tbody></table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "arithmetic_match")
        self.assertEqual(result["denominator"], 100)

    def test_abstains_when_table_has_multiple_unscoped_denominators(self):
        data = jats(
            '<table-wrap><caption><p>Overall N=50; complete-case n=48.</p></caption>'
            '<table><thead><tr><th>Reason</th><th>Patients n (%)</th></tr></thead>'
            '<tbody><tr><td>Reason A</td><td>4 (8.00)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "multiple_unscoped_table_denominators")
        self.assertIsNone(result["denominator"])

    def test_abstains_when_row_context_suggests_a_different_population(self):
        data = jats(
            '<table-wrap><caption><p>Participants (N=50).</p></caption>'
            '<table><thead><tr><th>Subgroup</th><th>Patients n (%)</th></tr></thead>'
            '<tbody><tr><td>Subgroup n=40</td><td>2 (4.00)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "row_level_denominator_scope_unclear")

    def test_uses_contract_half_up_rounding_at_a_tie(self):
        data = jats(
            '<table-wrap><caption><p>Analysis (N=32).</p></caption><table>'
            '<thead><tr><th>Reason</th><th>Patients, n (%)</th></tr></thead>'
            '<tbody><tr><td>Reason A</td><td>1 (3.13)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "arithmetic_match")
        self.assertEqual(result["contract_expected_percent"], "3.13")
        self.assertEqual(result["display_precision"], 2)

    def test_maps_a_complete_rowspan_and_colspan_header(self):
        data = jats(
            '<table-wrap><table><thead>'
            '<tr><th rowspan="2">Reason</th><th colspan="2">Group, N=50</th></tr>'
            '<tr><th>Patients n (%)</th><th>Other n (%)</th></tr>'
            '</thead><tbody><tr><td>Reason A</td><td>2 (4.00)</td>'
            '<td>1 (2.00)</td></tr></tbody></table></table-wrap>'
        )
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["status"] == "arithmetic_match" for item in results))
        self.assertEqual([item["denominator"] for item in results], [50, 50])

    def test_maps_distinct_hierarchical_populations_and_body_row_labels(self):
        data = jats('<table-wrap><table><thead>'
            '<tr><th rowspan="2">Category</th><th colspan="2">Arm A (N=40)</th>'
            '<th>Arm B (N=80)</th></tr><tr><th>n (%)</th><th>n (%)</th><th>n (%)</th></tr>'
            '</thead><tbody><tr><td rowspan="2">Outcome</td><td>4 (10%)</td><td>2 (5%)</td>'
            '<td>8 (10%)</td></tr><tr><td>0 (0.00%)</td><td>1 (2.50%)</td><td>1 (1.20%)</td></tr>'
            '</tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual([r["denominator"] for r in results], [40, 40, 80, 40, 40, 80])
        self.assertEqual(results[-1]["status"], "arithmetic_mismatch_candidate")
        for result in results:
            for source in result["evidence"]["denominator_sources"]:
                anchor = source["evidence"]
                self.assertIn(b"N=", data[anchor["byte_start"]:anchor["byte_end"]])

    def test_rejects_ragged_or_overrunning_header_scopes(self):
        for header in ['<tr><th rowspan="2">Label</th><th>N=40, n (%)</th></tr>',
                       '<tr><th>Label</th><th>N=40, n (%)</th></tr><tr><th>Label</th></tr>']:
            with self.subTest(header=header):
                data = jats('<table-wrap><table><thead>' + header + '</thead><tbody>'
                    '<tr><td>A</td><td>4 (10%)</td></tr></tbody></table></table-wrap>')
                result = audit_jats_percentage_tables(data)["results"][0]
                self.assertEqual(result["reason"], "unsupported_header_spans")
                self.assertIsNone(result["denominator"])

    def test_cross_tab_subgroup_percentages_require_an_explicit_basis(self):
        data = jats('<table-wrap><caption><p>Number (%)</p></caption><table><thead><tr>'
            '<th>Trait</th><th>No. of patients (N=80)</th><th>Arm A (N=30)</th>'
            '<th>Arm B (N=50)</th></tr></thead><tbody><tr><td>Trait A</td>'
            '<td>40 (50%)</td><td>12 (15%)</td><td>28 (35%)</td></tr></tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual(results[0]["status"], "arithmetic_match")
        self.assertEqual([r["reason"] for r in results[1:]], ["cross_tab_denominator_scope_unclear"] * 2)
        self.assertTrue(all(r["denominator"] is None for r in results[1:]))

    def test_explicit_group_markers_override_table_population_and_reset(self):
        data = jats('<table-wrap><caption><p>All participants N=100</p></caption><table>'
            '<thead><tr><th>Trait</th><th>n (%)</th></tr></thead><tbody>'
            '<tr><td colspan="2">Parents (N=40)</td></tr><tr><td>A</td><td>4 (10%)</td></tr>'
            '<tr><td colspan="2">Children (N=60)</td></tr><tr><td>B</td><td>6 (10%)</td></tr>'
            '</tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual([r["denominator"] for r in results], [40, 60])
        self.assertTrue(all(r["denominator_scope"] == "row_group" for r in results))

    def test_missing_data_returns_an_abstention_and_conditional_calculation(self):
        data = jats('<table-wrap><table><thead><tr><th>Category</th><th>N=100, n (%)</th>'
            '</tr></thead><tbody><tr><td colspan="2">Age</td></tr>'
            '<tr><td>Young</td><td>60 (6%)</td></tr><tr><td>Missing</td><td>1 (&lt;1%)</td></tr>'
            '<tr><td colspan="2">Region</td></tr><tr><td>North</td><td>50 (50%)</td></tr>'
            '</tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual(results[0]["reason"], "missing_data_denominator_scope_unclear")
        self.assertIsNone(results[0]["denominator"])
        self.assertEqual(results[0]["conditional_calculation"]["denominator"], 100)
        self.assertFalse(results[0]["conditional_calculation"]["arithmetic_matches"])
        self.assertEqual(results[-1]["status"], "arithmetic_match")

    def test_zero_missing_and_explicit_cell_ratios_do_not_lose_their_denominator(self):
        data = jats('<table-wrap><table><thead><tr><th>Trait</th><th>N=100, n (%)</th>'
            '</tr></thead><tbody><tr><td>A</td><td>0/40 (0.00%)</td></tr>'
            '<tr><td>B</td><td>0/0 (0.0%)</td></tr><tr><td>Missing</td><td>0 (0%)</td></tr>'
            '</tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual(results[0]["denominator"], 40)
        self.assertEqual(results[0]["status"], "arithmetic_match")
        self.assertEqual(results[1]["reason"], "nonpositive_denominator")
        self.assertEqual(results[2]["denominator"], 100)

    def test_extracts_labeled_components_with_exact_normalized_spans(self):
        data = jats('<table-wrap><caption><p>N=40</p></caption><table><tbody>'
            '<tr><td>A</td><td>P12(30%) C 8(20%)</td></tr></tbody></table></table-wrap>')
        report = audit_jats_percentage_tables(data)
        self.assertEqual([r["numerator"] for r in report["results"]], [12, 8])
        for result in report["results"]:
            evidence = result["evidence"]
            self.assertEqual(evidence["cell_quote"][evidence["normalized_character_start"]:
                evidence["normalized_character_end"]], evidence["relationship_quote"])
            self.assertIn(evidence["relationship_quote"].encode(), data[evidence["byte_start"]:evidence["byte_end"]])
            self.assertEqual(result["status"], "arithmetic_match")

    def test_does_not_partially_parse_labeled_components_or_assume_numeric_pairs_are_percentages(self):
        for cell in ['P12(30%) unexpected C8(20%) trailing',
                     'P12(30%) P8(20%)', 'P12(30) C8(20)']:
            with self.subTest(cell=cell):
                data = jats('<table-wrap><table><tbody><tr><td>A</td><td>' + cell + '</td>'
                    '</tr></tbody></table></table-wrap>')
                self.assertEqual(audit_jats_percentage_tables(data)["results"], [])
        data = jats('<table-wrap><table><thead><tr><th>Trait</th><th>Group (N=40)</th>'
            '</tr></thead><tbody><tr><td>Category A</td><td>12 (30)</td></tr></tbody></table></table-wrap>')
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["reason"], "percentage_context_not_explicit")
        self.assertIsNone(result["contract_expected_percent"])

    def test_scopes_adjustment_notes_only_with_valid_explicit_table_references(self):
        for rid, expected in [('weighted', ['arithmetic_match', 'scope_ambiguous']),
                              ('missing-id', ['scope_ambiguous', 'scope_ambiguous'])]:
            with self.subTest(rid=rid):
                data = jats('<p>Weighted percentages appear in <xref ref-type="table" rid="' + rid + '">Table 2</xref>.</p>'
                    + ''.join('<table-wrap id="' + tid + '"><caption><p>N=40</p></caption>'
                    '<table><tbody><tr><td>A</td><td>4 (10%)</td></tr></tbody></table></table-wrap>'
                    for tid in ['unweighted', 'weighted']))
                self.assertEqual([r["status"] for r in audit_jats_percentage_tables(data)["results"]], expected)

    def test_round_number_is_not_a_rounding_method_and_layout_expansion_is_bounded(self):
        data = jats('<table-wrap><caption><p>N=40</p></caption><table><tbody>'
            '<tr><td>Round 1</td><td>4 (10%)</td></tr></tbody></table></table-wrap>')
        self.assertEqual(audit_jats_percentage_tables(data)["results"][0]["status"], "arithmetic_match")
        wide = jats('<table-wrap><table><thead><tr>' + '<th colspan="64">N=40</th>' * 5
                    + '</tr></thead></table></table-wrap>')
        with self.assertRaisesRegex(JATSSourceError, "column-count"):
            audit_jats_percentage_tables(wide)

    def test_a_table_reference_does_not_narrow_a_general_adjustment_rule(self):
        data = jats('<p>All percentages are weighted. Counts are summarized in '
            '<xref ref-type="table" rid="t1">Table 1</xref>.</p>'
            + ''.join('<table-wrap id="' + tid + '"><caption><p>N=40</p></caption>'
            '<table><tbody><tr><td>A</td><td>4 (9%)</td></tr></tbody></table></table-wrap>'
            for tid in ['t1', 't2']))
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual([r["reason"] for r in results], ["adjustment_method_scope_not_mapped"] * 2)

    def test_conflicting_row_group_and_column_populations_abstain(self):
        data = jats('<table-wrap><table><thead><tr><th>Trait</th>'
            '<th>Male N=20, n (%)</th><th>Female N=20, n (%)</th></tr></thead><tbody>'
            '<tr><td colspan="3">Subpopulation N=40</td></tr>'
            '<tr><td>A</td><td>4 (20%)</td><td>4 (20%)</td></tr></tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual([r["reason"] for r in results], ["row_group_column_denominator_conflict"] * 2)
        self.assertTrue(all(r["denominator"] is None for r in results))

    def test_missing_counts_in_separate_columns_preserve_scope_uncertainty(self):
        data = jats('<table-wrap><caption><p>N=100</p></caption><table><thead>'
            '<tr><th>Category</th><th>n</th><th>%</th></tr></thead><tbody>'
            '<tr><td>A</td><td>60</td><td>60.61</td></tr>'
            '<tr><td>Missing</td><td>1</td><td>1.00</td></tr></tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual([r["reason"] for r in results], ["missing_data_denominator_scope_unclear"] * 2)
        self.assertTrue(all(r["denominator"] is None for r in results))

    def test_explicit_round_down_or_up_conventions_still_abstain(self):
        for note in ['We round down percentages to integers.', 'We round up values.',
                     'We round percentages to integers.']:
            with self.subTest(note=note):
                data = jats('<table-wrap><caption><p>N=6</p></caption><table><tbody>'
                    '<tr><td>A</td><td>1 (16%)</td></tr></tbody></table>'
                    '<table-wrap-foot><p>' + note + '</p></table-wrap-foot></table-wrap>')
                self.assertEqual(audit_jats_percentage_tables(data)["results"][0]["status"], "rounding_ambiguous")

    def test_conditional_calculation_cannot_override_a_conflicting_row_population(self):
        data = jats('<table-wrap><caption><p>N=100</p></caption><table><tbody>'
            '<tr><td>A N=80</td><td>60 (75%)</td></tr>'
            '<tr><td>Missing</td><td>1 (1%)</td></tr></tbody></table></table-wrap>')
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["reason"], "row_level_denominator_scope_unclear")
        self.assertNotIn("conditional_calculation", result)

    def test_long_table_identifiers_keep_their_adjustment_scope(self):
        tid = 't' * 150
        data = jats('<p>Weighted percentages appear in <xref ref-type="table" rid="' + tid + '">Table 1</xref>.</p>'
            '<table-wrap id="' + tid + '"><caption><p>N=40</p></caption><table><tbody>'
            '<tr><td>A</td><td>4 (9%)</td></tr></tbody></table></table-wrap>')
        self.assertEqual(audit_jats_percentage_tables(data)["results"][0]["reason"], "adjustment_method_scope_not_mapped")

    def test_inherited_rowspan_labels_preserve_denominator_conflicts(self):
        data = jats('<table-wrap><caption><p>N=100</p></caption><table><thead>'
            '<tr><th>Group</th><th>n (%)</th></tr></thead><tbody>'
            '<tr><td rowspan="2">Parents N=40</td><td>4 (10%)</td></tr>'
            '<tr><td>8 (20%)</td></tr></tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)['results']
        self.assertEqual([r['reason'] for r in results], ['row_level_denominator_scope_unclear'] * 2)
        self.assertTrue(all(r['denominator'] is None for r in results))
        self.assertIn('Parents N=40', results[1]['evidence']['row_context'])
        inherited = results[1]['evidence']['denominator_sources'][-1]['evidence']
        self.assertEqual(data[inherited['byte_start']:inherited['byte_end']], b'<td rowspan="2">Parents N=40</td>')

    def test_inherited_numeric_rowspans_remain_unsupported(self):
        data = jats('<table-wrap><caption><p>N=100</p></caption><table><tbody>'
            '<tr><td>A</td><td rowspan="2">4 (4%)</td><td>5 (5%)</td></tr>'
            '<tr><td>B</td><td>6 (6%)</td></tr></tbody></table></table-wrap>')
        results = audit_jats_percentage_tables(data)['results']
        self.assertEqual([r['reason'] for r in results], ['unsupported_data_cell_spans'] * 3)

    def test_group_size_does_not_override_explicit_table_percentage_basis(self):
        data = jats('<table-wrap><caption><p>All percentages use the full cohort denominator N=100, including subgroup rows.</p></caption>'
            '<table><tbody><tr><td colspan="2">Parents N=40</td></tr>'
            '<tr><td>A</td><td>4 (4%)</td></tr></tbody></table></table-wrap>')
        result = audit_jats_percentage_tables(data)['results'][0]
        self.assertEqual(result['reason'], 'conflicting_explicit_table_percentage_basis')
        self.assertIsNone(result['denominator'])
        self.assertNotIn('conditional_calculation', result)

    def test_generic_population_caption_still_allows_explicit_group_N(self):
        data = jats('<table-wrap><caption><p>Population N=100.</p></caption><table><tbody>'
            '<tr><td colspan="2">Parents N=40, n (%)</td></tr>'
            '<tr><td>A</td><td>4 (10%)</td></tr></tbody></table></table-wrap>')
        result = audit_jats_percentage_tables(data)['results'][0]
        self.assertEqual(result['status'], 'arithmetic_match')
        self.assertEqual(result['denominator'], 40)

    def test_decimal_N_does_not_become_integer_denominator(self):
        data = jats('<table-wrap><caption><p>N=40.5</p></caption><table><tbody>'
            '<tr><td>A</td><td>4 (10%)</td></tr></tbody></table></table-wrap>')
        self.assertEqual(audit_jats_percentage_tables(data)['results'][0]['reason'], 'no_explicit_denominator')

    def test_abstains_without_any_denominator_evidence(self):
        data = jats(
            '<table-wrap><table><thead><tr><th>Reason</th>'
            '<th>Patients n (%)</th></tr></thead><tbody><tr>'
            '<td>Reason A</td><td>4 (8.00)</td></tr></tbody></table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "no_explicit_denominator")

    def test_does_not_treat_mean_sd_cells_as_percentages_from_unrelated_caption(self):
        data = jats(
            '<table-wrap><caption><p>Threshold changed by 10% overall; N=50.</p></caption>'
            '<table><thead><tr><th>Parameter</th><th>Value (mean/SD)</th></tr></thead>'
            '<tbody><tr><td>Example measure</td><td>10 (2)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        self.assertEqual(report["percentage_cells_reviewed"], 0)
        self.assertEqual(report["results"], [])

    def test_does_not_apply_a_contract_rounding_rule_over_source_rounding_note(self):
        data = jats(
            '<table-wrap><caption><p>Analysis (N=32).</p></caption>'
            '<table><thead><tr><th>Reason</th><th>Patients n (%)</th></tr></thead>'
            '<tbody><tr><td>Reason A</td><td>1 (3.12)</td></tr></tbody></table>'
            '<table-wrap-foot><fn><p>Percentages were truncated for display.</p></fn></table-wrap-foot>'
            '</table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "rounding_ambiguous")
        self.assertEqual(result["reason"], "source_rounding_convention_not_modeled")
        self.assertIsNone(result["contract_expected_percent"])
        self.assertIn("truncated", result["evidence"]["rounding_note"])

    def test_abstains_when_document_mentions_unmapped_adjusted_percentages(self):
        data = jats(
            '<p>Categorical values may use adjusted percentage frequencies.</p>'
            '<table-wrap><caption><p>Analysis set N=50.</p></caption><table>'
            '<thead><tr><th>Reason</th><th>Patients n (%)</th></tr></thead>'
            '<tbody><tr><td>Reason A</td><td>4 (8.00)</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "adjustment_method_scope_not_mapped")
        self.assertIsNone(result["denominator"])
        notes = result["evidence"]["adjustment_notes"]
        self.assertEqual(notes[0]["role"], "document_method")
        self.assertIn("adjusted percentage frequencies", notes[0]["quote"])

    def test_supports_explicit_count_and_percent_columns(self):
        data = jats(
            '<table-wrap><caption><p>Analysis (N=50).</p></caption><table>'
            '<thead><tr><th>Reason</th><th>Count, n</th><th>Rate (%)</th></tr></thead>'
            '<tbody><tr><td>Reason A</td><td>2</td><td>4.00%</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "arithmetic_match")
        self.assertEqual(result["numerator"], 2)
        self.assertEqual(result["denominator"], 50)
        count_source = result["evidence"]["count_evidence"]
        self.assertEqual(count_source["role"], "count_cell")
        self.assertEqual(
            data[count_source["byte_start"]:count_source["byte_end"]],
            b"<td>2</td>",
        )

    def test_recognizes_percent_column_but_abstains_without_denominator(self):
        data = jats(
            '<table-wrap><table><thead><tr><th>Event</th><th>n</th><th>%</th></tr></thead>'
            '<tbody><tr><td>Event A</td><td>2</td><td>4.0</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "no_explicit_denominator")
        self.assertEqual(result["numerator"], 2)
        self.assertIsNone(result["denominator"])

    def test_abstains_with_evidence_when_per_row_denominator_cell_is_missing(self):
        data = jats(
            '<table-wrap><caption><p>Study population N=100.</p></caption><table>'
            '<thead><tr><th>Category</th><th>n</th><th>N</th><th>%</th></tr></thead>'
            '<tbody><tr><td>Group A</td><td>2</td><td></td><td>5.00</td></tr></tbody>'
            '</table></table-wrap>'
        )
        result = audit_jats_percentage_tables(data)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "row_specific_denominator_not_reported")
        self.assertIsNone(result["denominator"])
        self.assertEqual(result["numerator"], 2)
        self.assertEqual(result["evidence"]["row_denominator_header"][0]["quote"], "N")
        missing_cell = result["evidence"]["row_denominator_cell"]
        self.assertEqual(data[missing_cell["byte_start"]:missing_cell["byte_end"]], b"<td></td>")

    def test_recognizes_no_columns_and_one_explicit_full_width_table_total(self):
        data = jats(
            '<table-wrap id="total-row-scope"><table>'
            '<thead><tr><th colspan="6">Ward distribution of total admissions (%)</th></tr>'
            '<tr><th>Ward</th><th>No.</th><th>%</th>'
            '<th>Ward</th><th>No.</th><th>%</th></tr></thead><tbody>'
            '<tr><td>Ward A</td><td>542</td><td>5.63</td>'
            '<td>Ward B</td><td>205</td><td>4.13</td></tr>'
            '<tr><td>Ward C</td><td>6913</td><td>90.24</td>'
            '<td>Ward D</td><td>1</td><td>0.01</td></tr>'
            '<tr><td colspan="6">Total 7661 (100%)</td></tr>'
            '</tbody></table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        self.assertEqual(report["tables_inspected"], 1)
        self.assertEqual(len(report["results"]), 4)
        by_count = {result["numerator"]: result for result in report["results"]}
        self.assertEqual(
            {count: by_count[count]["status"] for count in (542, 205, 6913, 1)},
            {
                542: "arithmetic_mismatch_candidate",
                205: "arithmetic_mismatch_candidate",
                6913: "arithmetic_match",
                1: "arithmetic_match",
            },
        )
        self.assertEqual(by_count[542]["denominator"], 7661)
        self.assertEqual(by_count[542]["contract_expected_percent"], "7.07")
        self.assertEqual(by_count[205]["contract_expected_percent"], "2.68")
        self.assertEqual(by_count[542]["denominator_scope"], "table_total_row")
        source = by_count[542]["evidence"]
        count_anchor = source["count_evidence"]
        self.assertEqual(data[count_anchor["byte_start"]:count_anchor["byte_end"]], b"<td>542</td>")
        total_anchor = next(
            fact["evidence"] for fact in source["denominator_sources"]
            if fact["evidence"]["role"] == "table_total_row"
        )
        self.assertEqual(
            data[total_anchor["byte_start"]:total_anchor["byte_end"]],
            b'<td colspan="6">Total 7661 (100%)</td>',
        )

    def test_frequency_and_explicitly_qualified_uppercase_n_are_count_headers(self):
        cases = (
            ('<th>Frequency</th><th>Percent</th>', "5", "5.00", 100),
            ('<th>N (count)</th><th>%</th>', "3", "15.00", 20),
        )
        for headers, numerator, printed, denominator in cases:
            with self.subTest(headers=headers):
                data = jats(
                    f'<table-wrap><caption><p>Analysis population N={denominator}.</p></caption>'
                    f'<table><thead><tr><th>Category</th>{headers}</tr></thead>'
                    f'<tbody><tr><td>Category A</td><td>{numerator}</td>'
                    f'<td>{printed}</td></tr></tbody></table></table-wrap>'
                )
                results = audit_jats_percentage_tables(data)["results"]
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["status"], "arithmetic_match")
                self.assertEqual(results[0]["numerator"], int(numerator))
                self.assertEqual(results[0]["denominator"], denominator)

    def test_bare_uppercase_n_is_not_promoted_to_a_numerator(self):
        data = jats(
            '<table-wrap><table><thead><tr><th>Category</th><th>N</th><th>%</th></tr></thead>'
            '<tbody><tr><td>Category A</td><td>5</td><td>50.00</td></tr></tbody>'
            '</table></table-wrap>'
        )
        self.assertEqual(audit_jats_percentage_tables(data)["results"], [])

    def test_footer_total_is_not_a_denominator_without_explicit_total_percentage_scope(self):
        data = jats(
            '<table-wrap><table><thead><tr><th colspan="3">Ward counts and percentages</th></tr>'
            '<tr><th>Ward</th><th>No.</th><th>%</th></tr></thead><tbody>'
            '<tr><td>Ward A</td><td>5</td><td>50.00</td></tr>'
            '<tr><td>Ward B</td><td>5</td><td>50.00</td></tr>'
            '<tr><td colspan="3">Total 10 (100%)</td></tr>'
            '</tbody></table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        data_rows = [item for item in report["results"] if item["numerator"] == 5]
        self.assertEqual(len(data_rows), 2)
        self.assertTrue(all(item["denominator"] is None for item in data_rows))
        self.assertTrue(all(item["status"] == "scope_ambiguous" for item in data_rows))

    def test_multiple_full_width_totals_do_not_choose_a_denominator(self):
        data = jats(
            '<table-wrap><table><thead><tr><th colspan="3">Percent of total admissions (%)</th></tr>'
            '<tr><th>Ward</th><th>No.</th><th>%</th></tr></thead><tbody>'
            '<tr><td>Ward A</td><td>5</td><td>50.00</td></tr>'
            '<tr><td colspan="3">Total 10 (100%)</td></tr>'
            '<tr><td colspan="3">Total 20 (100%)</td></tr>'
            '</tbody></table></table-wrap>'
        )
        report = audit_jats_percentage_tables(data)
        candidate = next(item for item in report["results"] if item["numerator"] == 5)
        self.assertEqual(candidate["status"], "scope_ambiguous")
        self.assertIsNone(candidate["denominator"])

    def test_rejects_doctype_entities_and_malformed_xml(self):
        for data in (
            b'<!DOCTYPE article [<!ENTITY x "expanded">]><article><body>&x;</body></article>',
            b"<article><body>",
        ):
            with self.subTest(data=data), self.assertRaises(JATSSourceError):
                audit_jats_percentage_tables(data)

    def test_rejects_pdf_and_html_challenge_bytes_as_non_jats(self):
        for data in (b"%PDF-1.7\n", b"<!doctype html><html><title>Challenge</title></html>",
                     b"<html><title>Challenge</title></html>", b"<response>Not an article</response>"):
            with self.subTest(prefix=data[:8]), self.assertRaises(JATSSourceError):
                audit_jats_percentage_tables(data)

    def test_rejects_excessive_xml_nesting(self):
        data = ("<article>" + "<x>" * 260 + "text" + "</x>" * 260 + "</article>").encode()
        with self.assertRaises(JATSSourceError):
            audit_jats_percentage_tables(data)

    def test_non_table_jats_is_a_hashed_empty_result(self):
        data = b"<article><body><p>Nothing tabular here.</p></body></article>"
        report = audit_jats_percentage_tables(data)
        self.assertEqual(report["tables_inspected"], 0)
        self.assertEqual(report["results"], [])
        self.assertEqual(report["source_sha256"], hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
