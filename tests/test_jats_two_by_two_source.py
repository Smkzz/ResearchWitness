"""RW-01F source-mapped unadjusted 2x2 JATS ratio regression tests.

All source material is synthetic. These assertions do not measure empirical
scientific discovery, source authenticity or study-level ground truth.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import jats_product
from researchwitness.jats_table_projection import project_jats_tables
from researchwitness import paper_two_by_two_source as ratio

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/synthetic-jats/odds-ratio.xml"


def source() -> bytes:
    return FIXTURE.read_bytes()


def examine(data: bytes) -> dict:
    return ratio.check_jats_unadjusted_2x2_tables(project_jats_tables(data))


def swap(data: bytes, old: bytes, new: bytes) -> bytes:
    assert data.count(old) == 1
    return data.replace(old, new)


def test_original_xml_cells_are_used_for_crude_odds_ratio():
    raw = source()
    doc = project_jats_tables(raw)
    assert doc.tables[0].structure_status == "mapped_not_adjudicated"
    assert doc.tables[0].rows[0].row_group.startswith("tbody:")
    result = ratio.check_jats_unadjusted_2x2_tables(doc)
    assert result["scan_complete"] is True
    assert result["tables"][0]["status"] == "ELIGIBLE"
    assert result["tables"][0]["checked_objects"] == 1
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["status"] == "CANDIDATE_ANOMALY"
    assert finding["exact_numerator"] == "47"
    assert finding["exact_denominator"] == "22"
    assert finding["recomputed_at_display_precision"] == "2.14"
    assert finding["reported_odds_ratio"] == "2.20"
    assert finding["row_identity"] == "30-day mortality"
    assert finding["type"] == "JATS_UNADJUSTED_2X2_ODDS_RATIO_MISMATCH"
    assert len(finding["source_anchors"]) == 5
    for anchor in finding["source_anchors"] + [finding["row_context_anchor"]]:
        assert anchor["source_sha256"] == sha256(raw).hexdigest()
        assert anchor["source_format"] == "jats_xml"
        text = raw[anchor["start_byte"]:anchor["end_byte"]]
        assert text.startswith(b"<td") or text.startswith(b"<th")


def test_consistent_report_is_checked_but_not_called_error():
    result = examine(swap(source(), b"<td>2.20</td>", b"<td>2.14</td>"))
    assert result["scan_complete"] is True
    assert result["tables"][0]["status"] == "ELIGIBLE"
    assert result["tables"][0]["checks"][0]["status"] == "CONSISTENT_WITH_ROUNDING"
    assert result["findings"] == []


@pytest.mark.parametrize(("old", "new", "expected"), [
    (b"Unadjusted odds ratio", b"Adjusted odds ratio", "NOT_APPLICABLE"),
    (b"Invented independent groups: 30-day mortality comparison",
     b"Invented weighted independent groups: 30-day mortality comparison", "UNSUPPORTED"),
    (b"Invented independent groups: 30-day mortality comparison",
     b"Invented matched independent groups: 30-day mortality comparison", "UNSUPPORTED"),
    (b"Invented independent groups: 30-day mortality comparison",
     b"Invented 30-day mortality comparison", "INCOMPLETE"),
    (b"30-day mortality", b"outcome mortality", "UNSUPPORTED"),
    (b"<td>12</td>", b"<td>12.0</td>", "INCOMPLETE"),
    (b"<td>12</td>", b"<td>0</td>", "UNSUPPORTED"),
    (b"<td>2.20</td>", b"<td>2.20 (1.90 to 2.50)</td>", "INCOMPLETE"),
])
def test_hard_negatives_do_not_create_false_candidate(old, new, expected):
    raw = source()
    if old == b"30-day mortality":
        # Remove both the caption and row timepoint.
        raw = raw.replace(old, new)
    else:
        raw = swap(raw, old, new)
    result = examine(raw)
    assert result["findings"] == []
    assert result["tables"][0]["status"] == expected
    if expected in {"UNSUPPORTED", "INCOMPLETE"}:
        assert result["scan_complete"] is False


def test_multirow_or_auxiliary_column_does_not_silently_skip_data():
    raw = source()
    duplicate = raw.replace(
        b"</tr></tbody></table>",
        b'<tr><th scope="row">30-day mortality</th>'
        b"<td>12</td><td>88</td><td>6</td><td>94</td><td>2.20</td>"
        b"</tr></tr></tbody></table>",
    )
    # Nested table rows are XML-parseable but not a valid supported layout.
    # Failure here must be explicit incomplete coverage, not a false positive.
    nested = examine(duplicate)
    assert nested["findings"] == []
    assert nested["scan_complete"] is False
    good_second = raw.replace(
        b"</tr></tbody></table>",
        b'</tr><tr><th scope="row">30-day mortality</th>'
        b"<td>12</td><td>88</td><td>6</td><td>94</td><td>2.20</td>"
        b"</tr></tbody></table>",
    )
    report = examine(good_second)
    assert report["findings"] == []
    assert report["tables"][0]["skip_reasons"][0]["reason"] == "ONE_OUTCOME_ROW_REQUIRED"

    too_many = raw.replace(
        b"<th>Unexposed non-event</th>",
        b"<th>Unexposed non-event</th><th>Extra arm</th>",
    ).replace(
        b"<td>94</td>", b"<td>94</td><td>77</td>",
    )
    result = examine(too_many)
    assert not result["findings"]
    assert result["tables"][0]["status"] == "UNSUPPORTED"


def test_header_span_footnote_and_source_scope_are_fail_closed():
    raw = source()
    span = swap(raw, b"<th>Exposed event</th>", b'<th colspan="2">Exposed event</th>')
    assert not examine(span)["findings"]
    notes = swap(raw, b"</table-wrap>", b"<table-wrap-foot><fn id='f1'>Adjusted weights</fn></table-wrap-foot></table-wrap>")
    notes_report = examine(notes)
    assert notes_report["findings"] == []
    assert not notes_report["scan_complete"]

    caption_n = swap(raw, b"Invented independent groups: 30-day mortality comparison",
                     b"Invented independent groups: 30-day mortality comparison (N=100)")
    assert not examine(caption_n)["findings"]
    conditional = swap(raw, b'id="synthetic-or"',
                       b'id="synthetic-or" specific-use="conditional"')
    assert not examine(conditional)["findings"]


def test_structural_ambiguity_never_qualifies_candidate():
    raw = source()
    duplicated = raw.replace(b"<table-wrap id=\"synthetic-or\">",
                             b'<table-wrap id="synthetic-or">', 1)
    duplicated = duplicated.replace(b"</body>", raw.split(b"<body>")[1].split(b"</body>")[0] + b"</body>")
    report = examine(duplicated)
    assert not report["findings"]
    assert any(item["status"] == "INCOMPLETE" for item in report["tables"])


def test_optional_installed_report_and_replay_do_not_change_default(tmp_path):
    unstructured = tmp_path / "default"
    jats_product.audit_source(FIXTURE, unstructured, "synthetic")
    assert "odds_ratio_review" not in json.loads((unstructured / "report.json").read_bytes())

    reviewed = tmp_path / "reviewed"
    created = jats_product.audit_source(FIXTURE, reviewed, "synthetic",
                                        include_odds_ratio=True)
    report = json.loads((reviewed / "report.json").read_bytes())
    assert "table_projection" not in report
    assert len(report["odds_ratio_review"]["findings"]) == 1
    assert report["paper_error_established"] is False
    assert report["external_actions"] == "OUT_OF_SCOPE"
    assert "Opt-in unadjusted" in (reviewed / "report.html").read_text(encoding="utf-8")
    replay = jats_product.replay_bundle(reviewed, created["manifest_sha256"])
    assert replay["status"] == "verified"


def test_both_projection_and_2x2_replay_from_same_source(tmp_path):
    target = tmp_path / "both"
    result = jats_product.audit_source(FIXTURE, target, "synthetic",
                                       include_structure=True, include_odds_ratio=True)
    report = json.loads((target / "report.json").read_bytes())
    assert report["table_projection"]["source_sha256"] == sha256(source()).hexdigest()
    assert len(report["odds_ratio_review"]["findings"]) == 1
    assert jats_product.replay_bundle(target, result["manifest_sha256"])["status"] == "verified"


def test_rehashed_modified_ratio_report_cannot_pass_source_replay(tmp_path):
    target = tmp_path / "reviewed"
    jats_product.audit_source(FIXTURE, target, "synthetic", include_odds_ratio=True)
    doc = json.loads((target / "report.json").read_bytes())
    doc["odds_ratio_review"]["findings"][0]["reported_odds_ratio"] = "99.99"
    modified = jats_product.canonical_json(doc)
    (target / "report.json").write_bytes(modified)
    manifest = json.loads((target / "manifest.json").read_bytes())
    manifest["files"]["report.json"] = {
        "sha256": jats_product.digest(modified), "bytes": len(modified),
    }
    (target / "manifest.json").write_bytes(jats_product.canonical_json(manifest))
    with pytest.raises(ValueError, match="replay disagrees"):
        jats_product.replay_bundle(target)


def test_untrusted_row_label_is_escaped_in_html(tmp_path):
    raw = swap(source(), b"30-day mortality</th>",
               b"30-day mortality &lt;script&gt;alert(1)&lt;/script&gt;</th>")
    filename = tmp_path / "article.xml"
    filename.write_bytes(raw)
    target = tmp_path / "review"
    jats_product.audit_source(filename, target, "synthetic", include_odds_ratio=True)
    html = (target / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_cli_opt_in_and_missing_data_return_limited_results(tmp_path):
    output = tmp_path / "cli"
    result = subprocess.run([
        sys.executable, "-m", "researchwitness", "audit-jats",
        str(FIXTURE), "--document-id", "synthetic", "--output-dir", str(output),
        "--include-unadjusted-2x2",
    ], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "report.json").read_bytes())["odds_ratio_review"]["findings"]
    replay = subprocess.run([
        sys.executable, "-m", "researchwitness", "replay-jats", str(output),
    ], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert replay.returncode == 0, replay.stderr


def test_candidate_cap_reports_incomplete_not_perfect_review(monkeypatch):
    monkeypatch.setattr(ratio, "MAX_FINDINGS", 0)
    result = examine(source())
    assert result["findings"] == []
    assert result["scan_complete"] is False
    assert result["tables"][0]["status"] == "INCOMPLETE"
    assert "2X2_CANDIDATE_LIMIT" in result["limitations"]
