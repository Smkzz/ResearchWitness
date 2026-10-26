"""RW-01D: rich JATS table projection never invents scientific context."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import _jats_parser as jats
from researchwitness.jats_table_projection import project_jats_tables
from researchwitness.jats_product import audit_source, replay_bundle

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/synthetic-jats/article.xml"


def test_current_synthetic_fixture_source_bound_tables():
    source = FIXTURE.read_bytes()
    doc = project_jats_tables(source)
    assert doc.model_version == "rw-jats-table-projection.v1"
    assert doc.source_sha256 == sha256(source).hexdigest()
    assert doc.sections == () and doc.paragraphs == ()
    assert len(doc.tables) == 2
    assert len(doc.numeric_assertions) == 3
    assert doc.tables[0].label == "Table 1"
    assert doc.tables[0].structure_status == "mapped_not_adjudicated"
    assert doc.tables[0].caption == "Synthetic analysis set (N=50)."
    assert doc.tables[0].columns[1].header_hierarchy == ("Patients, n (%)",)
    first = doc.tables[0].rows[0].cells[1]
    assert first.raw_text == "4 (8.00)"
    assert [(n.surface, n.unit) for n in first.normalized_numeric_values] == [
        ("4", "count"), ("8.00", "percent")
    ]
    assert first.effective_headers == ("Patients, n (%)",)
    assert first.source_anchor.element_path.endswith("/tbody[1]/tr[1]/td[2]")
    anchor = first.source_anchor
    assert source[anchor.start_byte:anchor.end_byte] == b"<td>4 (8.00)</td>"
    assert anchor.source_sha256 == sha256(source).hexdigest()
    assertions = doc.numeric_assertions
    assert [a.denominator for a in assertions] == ["50", "50", None]
    assert [a.value for a in assertions] == ["8.00", "8.10", "8.00"]
    assert all(a.identity_key is None for a in assertions)
    assert all(a.population is None and a.adjustment_status is None for a in assertions)
    assert "detector_status:scope_ambiguous" in assertions[-1].structural_provenance
    assert doc.to_dict()["tables"][0]["rows"][0]["cells"][1]["raw_text"] == "4 (8.00)"


def rich_jats():
    return ("""
    <article><front><article-meta><title-group>
      <article-title>Structure fixture</article-title>
    </title-group></article-meta></front><body>
    <table-wrap id="T1"><label>Table Ä</label><caption><p>Invented values.</p></caption>
    <table><thead>
    <tr><th rowspan="2">Group</th><th colspan="2">Metrics</th></tr>
    <tr><th>Count</th><th>Percentage</th></tr>
    </thead><tbody>
    <tr><td>Arm 1</td><td>4</td><td>8.00</td></tr>
    <tr><td>Arm 2</td><td>3</td><td>6.00<xref ref-type="table-fn" rid="f1">a</xref></td></tr>
    </tbody></table>
    <table-wrap-foot><fn id="f1"><label>a</label><p>Not adjusted.</p></fn></table-wrap-foot>
    </table-wrap></body></article>""").encode("utf-8")


def test_header_spans_footnotes_and_untrusted_lexemes():
    source = rich_jats()
    doc = project_jats_tables(source)
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert table.label == "Table Ä"
    assert table.source_anchor.source_sha256 == sha256(source).hexdigest()
    assert table.structure_status == "mapped_not_adjudicated"
    assert "Group" in table.columns[0].header_hierarchy
    assert table.columns[1].header_hierarchy == ("Metrics", "Count")
    assert table.columns[2].header_hierarchy == ("Metrics", "Percentage")
    rawcount = table.rows[0].cells[1]
    assert rawcount.normalized_numeric_values[0].unit == "count"
    rawpercent = table.rows[0].cells[2]
    assert rawpercent.normalized_numeric_values[0].unit == "percent"
    assert rawpercent.effective_header_refs[-1].source_anchor.element_path.endswith("/thead[1]/tr[2]/th[2]")
    assert rawpercent.effective_header_refs[0].column_span == 2
    assert rawpercent.effective_header_refs[0].row_index == 0
    assert table.rows[1].cells[2].footnote_references == ("f1",)
    assert table.footnotes[0].identifier == "f1"
    assert table.footnotes[0].label == "a"
    assert source[table.rows[1].cells[2].source_anchor.start_byte:
                  table.rows[1].cells[2].source_anchor.end_byte].startswith(b"<td>6.00")
    assert "Not adjusted." in table.footnotes[0].text


def test_duplicate_source_table_identifiers_are_not_silently_conflated():
    source = (b"<article><body>" +
              b"<table-wrap id='same'><table><tr><td>A</td></tr></table></table-wrap>" * 2 +
              b"</body></article>")
    doc = project_jats_tables(source)
    assert [table.table_id for table in doc.tables] == ["same#1", "same#2"]
    assert all("duplicate_source_table_id" in table.limitations for table in doc.tables)
    assert all(table.structure_status == "ambiguous" for table in doc.tables)


def test_malformed_spans_abstain_instead_of_claiming_reliable_layout():
    data = (b"<article><table-wrap><table><thead><tr><th>Outcome</th>"
            b"<th>n (%)</th></tr></thead><tbody><tr>"
            b"<td rowspan='999'>Row</td><td>4 (8.00)</td>"
            b"</tr></tbody></table></table-wrap></article>")
    doc = project_jats_tables(data)
    assert doc.tables[0].structure_status == "ambiguous"
    assert "body_layout_ambiguous" in doc.tables[0].limitations


def test_missing_header_is_not_guesswork():
    data = (b"<article><table-wrap><table><tbody><tr>"
            b"<td>Outcome</td><td>4 (8.00)</td>"
            b"</tr></tbody></table></table-wrap></article>")
    doc = project_jats_tables(data)
    assert doc.tables[0].structure_status == "ambiguous"
    assert "explicit_header_not_available" in doc.tables[0].limitations
    assert all(cell.effective_headers == () for row in doc.tables[0].rows for cell in row.cells)


def test_wrong_source_version_in_detector_report_rejected():
    data = FIXTURE.read_bytes()
    report = jats.audit_jats_percentage_tables(data)
    report["source_sha256"] = "0" * 64
    with pytest.raises(jats.JATSSourceError, match="different bytes"):
        project_jats_tables(data, report)


def test_model_row_limit_refuses_instead_of_truncating(monkeypatch):
    import researchwitness.jats_table_projection as module
    monkeypatch.setattr(module, "MAX_MODEL_ROWS", 1)
    with pytest.raises(jats.JATSSourceError, match="row/cell limit"):
        module.project_jats_tables(FIXTURE.read_bytes())


def test_installed_opt_in_structure_roundtrip(tmp_path):
    bundle = tmp_path / "review"
    created = audit_source(FIXTURE, bundle, "synthetic", include_structure=True)
    report = json.loads((bundle / "report.json").read_bytes())
    assert report["table_projection"]["model_version"] == "rw-jats-table-projection.v1"
    assert len(report["table_projection"]["tables"]) == 2
    assert created["summary"] == {"arithmetic_matches": 1, "mismatch_candidates": 1, "abstentions": 1}
    assert replay_bundle(bundle, created["manifest_sha256"])["status"] == "verified"
    # A second independent audit without structure still works unchanged.
    no_model = tmp_path / "plain"
    created2 = audit_source(FIXTURE, no_model, "synthetic")
    assert "table_projection" not in json.loads((no_model / "report.json").read_bytes())
    assert replay_bundle(no_model, created2["manifest_sha256"])["status"] == "verified"


def test_structure_modified_even_with_rehashed_payload_fails_replay(tmp_path):
    from researchwitness.jats_product import canonical_json, digest
    bundle = tmp_path / "review"
    audit_source(FIXTURE, bundle, "synthetic", include_structure=True)
    report_path = bundle / "report.json"
    report = json.loads(report_path.read_bytes())
    report["table_projection"]["tables"][0]["rows"][0]["cells"][1]["raw_text"] = "FAKED"
    changed = canonical_json(report)
    report_path.write_bytes(changed)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"]["report.json"] = {"sha256": digest(changed), "bytes": len(changed)}
    manifest_path.write_bytes(canonical_json(manifest))
    with pytest.raises(ValueError, match="replay disagrees"):
        replay_bundle(bundle)


def test_cli_include_structure(tmp_path):
    output = tmp_path / "review"
    process = subprocess.run(
        [sys.executable, "-m", "researchwitness", "audit-jats", str(FIXTURE),
         "--document-id", "synthetic", "--output-dir", str(output), "--include-structure"],
        cwd=ROOT, text=True, capture_output=True, timeout=25,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads((output / "report.json").read_bytes())
    assert "table_projection" in report
    process = subprocess.run(
        [sys.executable, "-m", "researchwitness", "replay-jats", str(output)],
        cwd=ROOT, text=True, capture_output=True, timeout=25,
    )
    assert process.returncode == 0, process.stderr


def test_no_doctype_or_missing_source_bytes_enter_model():
    source = b'<!DOCTYPE article SYSTEM "file:///private"><article/>'
    with pytest.raises(jats.JATSSourceError):
        project_jats_tables(source)


def test_sd_not_misclassified_as_count_percent():
    source = (b"<article><table-wrap><table><thead><tr>"
              b"<th>Mean (SD)</th></tr></thead><tbody><tr>"
              b"<td>4 (8.00)</td></tr></tbody></table></table-wrap></article>")
    model = project_jats_tables(source)
    items = model.tables[0].rows[0].cells[0].normalized_numeric_values
    assert [item.surface for item in items] == ["4", "8.00"]
    assert [item.unit for item in items] == [None, None]


def test_spanning_body_cell_preserves_all_header_refs_without_inferred_roles():
    source = (b"<article><table-wrap><table><thead><tr>"
              b"<th>Count</th><th>Percentage</th></tr></thead><tbody><tr>"
              b"<td colspan='2'>4</td></tr></tbody></table></table-wrap></article>")
    model = project_jats_tables(source)
    table = model.tables[0]
    cell = table.rows[0].cells[0]
    assert cell.effective_headers == ("Count", "Percentage")
    assert [h.text for h in cell.effective_header_refs] == ["Count", "Percentage"]
    assert cell.normalized_numeric_values[0].unit is None
    assert "spanning_cell_role_ambiguous" in table.limitations
    assert table.structure_status == "ambiguous"


@pytest.mark.parametrize(("part","value"), [
    ("reported_percent", "99.99"),
    ("numerator", 99),
    ("denominator", 5),
    ("status", "arithmetic_match"),
])
def test_supplied_detector_result_cannot_forge_numeric_assertion(part, value):
    source = FIXTURE.read_bytes()
    detector = jats.audit_jats_percentage_tables(source)
    changed = deepcopy(detector)
    changed["results"][1][part] = value
    assert changed["source_sha256"] == sha256(source).hexdigest()
    with pytest.raises(jats.JATSSourceError, match="does not match source"):
        project_jats_tables(source, changed)


def test_supplied_denominator_role_and_value_cannot_be_forged():
    source = FIXTURE.read_bytes()
    changed = deepcopy(jats.audit_jats_percentage_tables(source))
    target = changed["results"][0]["evidence"]["denominator_sources"][0]
    target["value"] = 999
    with pytest.raises(jats.JATSSourceError, match="does not match source"):
        project_jats_tables(source, changed)
