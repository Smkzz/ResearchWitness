"""Strict, source-bound count-only JATS category total arithmetic regressions."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import jats_product
from researchwitness.jats_table_projection import project_jats_tables
from researchwitness.paper_count_totals import check_explicit_participant_totals

ROOT = Path(__file__).resolve().parents[1]


def xml(*, total="99", a="40", b="60", caption=None,
        header="Number of participants", row_a="Group A", row_b="Group B",
        footnote="", rows_extra="", row_label="Total", attrs=""):
    if caption is None:
        caption = (
            "Mutually exclusive and exhaustive categories of participants "
            "in cohort Alpha."
        )
    return (
        f'<article><body><table-wrap id="demographics"><label>Table 1</label>'
        f'<caption><p>{caption}</p></caption>'
        f'{footnote}<table><thead><tr><th>Category</th><th>{header}</th>'
        f'</tr></thead><tbody>'
        f'<tr><td {attrs}>{row_a}</td><td>{a}</td></tr>'
        f'<tr><td>{row_b}</td><td>{b}</td></tr>'
        f'{rows_extra}'
        f'<tr><td>{row_label}</td><td>{total}</td></tr>'
        f'</tbody></table></table-wrap></body></article>'
    ).encode("utf-8")


def scan(data):
    return check_explicit_participant_totals(project_jats_tables(data))


def test_explicit_disjoint_categories_produce_arithmetic_candidate_with_original_anchors():
    source = xml()
    report = scan(source)
    assert report["schema_version"] == "rw-jats-explicit-participant-total.v1"
    assert report["candidate_count"] == 1
    assert report["checked_table_count"] == 1
    case = report["cases"][0]
    assert case["status"] == "COUNT_TOTAL_MISMATCH_CANDIDATE"
    assert case["computed_total_exact"] == "100"
    assert case["reported_total_exact"] == "99"
    assert case["difference_exact"] == "-1"
    assert [x["count_exact"] for x in case["category_operands"]] == ["40", "60"]
    assert all(x["source_anchor"]["start_byte"] is not None
               and x["source_anchor"]["end_byte"] is not None
               and x["source_anchor"]["source_sha256"] ==
               case["total_anchor"]["source_sha256"]
               for x in case["category_operands"])
    assert all(x["source_anchor"]["element_path"].endswith("/td[2]")
               for x in case["category_operands"])
    assert report["scientific_error_established"] is False
    assert report["whole_paper_coverage_established"] is False


def test_correct_total_and_grouped_nonzero_counts():
    good = scan(xml(total="1,000", a="400", b="600"))
    assert good["checked_table_count"] == 1
    assert good["candidate_count"] == 0
    assert good["cases"][0]["status"] == "COUNT_TOTAL_MATCH"
    assert good["cases"][0]["computed_total_exact"] == "1000"


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"caption": "Counts of participants by group."},
     "EXHAUSTIVE_DISJOINT_SOURCE_DECLARATION_MISSING"),
    ({"caption": "Not mutually exclusive and exhaustive categories of participants."},
     "SOURCE_SCOPE_CONFLICT"),
    ({"caption": "Mutually exclusive and exhaustive categories of participants, "
                 "but an overlapping multiple-response subgroup is included."},
     "SOURCE_SCOPE_CONFLICT"),
    ({"caption": "Mutually exclusive and exhaustive categories of participants, "
                 "weighted counts by design."},
     "SOURCE_SCOPE_CONFLICT"),
    ({"caption": "Mutually exclusive and exhaustive categories of participants, "
                 "with missing data."},
     "SOURCE_SCOPE_CONFLICT"),
    ({"total": "98%"},
     "COUNT_OPERAND_OR_CATEGORY_INVALID"),
    ({"a": "12,00"},
     "COUNT_OPERAND_OR_CATEGORY_INVALID"),
    ({"a": "1000000000"},
     "COUNT_OPERAND_OR_CATEGORY_INVALID"),
    ({"row_a": "Missing"},
     "COUNT_OPERAND_OR_CATEGORY_INVALID"),
    ({"row_label": "All participants"},
     "FINAL_UNIQUE_TOTAL_ROW_REQUIRED"),
    ({"rows_extra": "<tr><td>Group A</td><td>3</td></tr>"},
     "COUNT_OPERAND_OR_CATEGORY_INVALID"),
    ({"rows_extra": "<tr><td>Total</td><td>40</td></tr>"},
     "COUNT_OPERAND_OR_CATEGORY_INVALID"),
    ({"footnote": "<table-wrap-foot><fn><p>Some excluded cases.</p></fn></table-wrap-foot>"},
     "UNRESOLVED_TABLE_STRUCTURE_OR_FOOTNOTES"),
    ({"attrs": "rowspan='2'"},
     "UNRESOLVED_TABLE_STRUCTURE_OR_FOOTNOTES"),
])
def test_ineligible_or_unsafe_tables_abstain(kwargs, reason):
    report = scan(xml(**kwargs))
    assert report["candidate_count"] == 0
    assert report["checked_table_count"] == 0
    assert report["cases"][0]["status"] == "UNSUPPORTED"
    assert report["cases"][0]["reason"] == reason
    assert report["cases"][0]["scientific_error_established"] is False


def test_unrelated_table_is_not_false_checked():
    report = scan(xml(header="Percent of respondents"))
    assert report["candidate_count"] == 0
    assert report["status_counts"]["NOT_APPLICABLE"] == 1


def test_multi_table_counts_and_incomplete_scopes_remain_visible():
    first = xml(total="100")
    second = xml(caption="No declaration of exclusivity.")
    source = first.replace(b"</body></article>", second[second.index(b"<table-wrap"):second.index(
        b"</body></article>")] + b"</body></article>")
    # Source IDs duplicated, which the current JATS projection identifies as
    # ambiguous rather than accepting either as independent authority.
    report = scan(source)
    assert report["tables_seen"] == 2
    assert report["candidate_count"] == 0
    assert report["status_counts"]["UNSUPPORTED"] == 2


def test_non_independent_row_groups_abstain():
    raw = xml()
    raw = raw.replace(b"</tbody></table>", b"</tbody><tfoot><tr>"
                      b"<td>Subtotal</td><td>10</td></tr></tfoot></table>")
    result = scan(raw)
    assert result["candidate_count"] == 0
    assert result["cases"][0]["status"] == "UNSUPPORTED"


def test_report_is_opt_in_and_preserves_existing_base_percentage_summary():
    source = xml()
    plain = jats_product.make_report(source, "demo", False)
    opted = jats_product.make_report(source, "demo", True, include_count_totals=True)
    assert "count_total_review" not in plain
    assert opted["summary"] == plain["summary"]
    assert opted["count_total_review"]["candidate_count"] == 1
    assert opted["paper_error_established"] is False
    assert opted["external_actions"] == "OUT_OF_SCOPE"


def test_source_mapped_html_escapes_untrusted_category_text_and_bundle_replays(tmp_path):
    source = xml(row_a="&lt;script&gt;alert(1)&lt;/script&gt;")
    original = tmp_path / "source.xml"
    original.write_bytes(source)
    bundle = tmp_path / "out"
    result = jats_product.audit_source(
        original, bundle, "demo", include_count_totals=True,
    )
    saved = json.loads((bundle / "report.json").read_bytes())
    assert saved["count_total_review"]["candidate_count"] == 1
    html = (bundle / "report.html").read_text("utf-8")
    assert "Opt-in explicit participant count-total review" in html
    assert "<script>" not in html
    assert "not confirmed research errors" in html
    assert jats_product.replay_bundle(bundle, result["manifest_sha256"])["status"] == (
        "verified"
    )
    report = bundle / "report.json"
    report.write_bytes(report.read_bytes() + b"evil")
    with pytest.raises(ValueError):
        jats_product.replay_bundle(bundle, result["manifest_sha256"])


def test_installed_cli_opt_in_and_exact_report_replay(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(xml())
    out = tmp_path / "audited"
    cmd = [sys.executable, "-m", "researchwitness", "audit-jats", str(source),
           "--output-dir", str(out), "--document-id", "count-total-demo",
           "--include-count-totals"]
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=40)
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    report = json.loads((out / "report.json").read_bytes())
    assert report["count_total_review"]["candidate_count"] == 1
    assert report["paper_error_established"] is False
    receipt = json.loads(done.stdout)
    replay = subprocess.run([
        sys.executable, "-m", "researchwitness", "replay-jats", str(out),
        "--expected-manifest-sha256", receipt["manifest_sha256"],
    ], cwd=ROOT, capture_output=True, timeout=40)
    assert replay.returncode == 0, replay.stderr.decode(errors="replace")
    assert json.loads(replay.stdout)["status"] == "verified"
