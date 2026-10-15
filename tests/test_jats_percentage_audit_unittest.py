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

    def test_abstains_when_rowspan_makes_denominator_column_scope_unclear(self):
        data = jats(
            '<table-wrap><table><thead>'
            '<tr><th rowspan="2">Reason</th><th colspan="2">Group, N=50</th></tr>'
            '<tr><th>Patients n (%)</th><th>Other n (%)</th></tr>'
            '</thead><tbody><tr><td>Reason A</td><td>2 (4.00)</td>'
            '<td>1 (2.00)</td></tr></tbody></table></table-wrap>'
        )
        results = audit_jats_percentage_tables(data)["results"]
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["status"] == "scope_ambiguous" for item in results))
        self.assertTrue(all(item["reason"] == "unsupported_header_spans" for item in results))

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

    def test_rejects_doctype_entities_and_malformed_xml(self):
        for data in (
            b'<!DOCTYPE article [<!ENTITY x "expanded">]><article><body>&x;</body></article>',
            b"<article><body>",
        ):
            with self.subTest(data=data), self.assertRaises(JATSSourceError):
                audit_jats_percentage_tables(data)

    def test_rejects_pdf_and_html_challenge_bytes_as_non_jats(self):
        for data in (b"%PDF-1.7\n", b"<!doctype html><html><title>Challenge</title></html>"):
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
