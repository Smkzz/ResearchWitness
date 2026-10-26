"""RW-01I: trace EXISTING JATS denominator decisions to original XML elements.

All cases use synthetic developer-exposed XML; no real-paper label or
scientific-denominator validation is asserted by these software tests.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import _jats_parser as jats
from researchwitness import jats_denominator_trace as traced
from researchwitness import jats_product

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/synthetic-jats/denominator-trace.xml"


def source() -> bytes:
    return FIXTURE.read_bytes()


def test_trace_all_existing_decisions_without_scientific_promotion():
    data = source()
    detector = jats.audit_jats_percentage_tables(data)
    trace = traced.trace_denominators(data, detector)
    assert trace["schema_version"] == "rw-jats-denominator-evidence.v1"
    assert trace["relation_count"] == detector["percentage_cells_reviewed"] == 3
    assert trace["fact_count"] >= 2
    assert trace["unresolved_relation_count"] == 1
    assert trace["source_sha256"] == sha256(data).hexdigest()
    assert trace["source_origin_authenticated"] is False
    assert trace["paper_error_established"] is False
    assert trace["full_article_denominator_provenance_established"] is False
    assert [row["detector_status"] for row in trace["relations"]] == [
        relation["status"] for relation in detector["results"]
    ]
    assert len({row["relation_id"] for row in trace["relations"]}) == 3
    assert all(row["scientific_denominator_scope_independently_adjudicated"] is False
               for row in trace["relations"])


def test_reported_base_binds_exact_original_source_element():
    data = source()
    review = traced.trace_denominators(data)
    rows = review["relations"]
    assert rows[0]["detector_denominator"] == 50
    assert rows[1]["detector_denominator"] == 233
    assert rows[1]["detector_denominator_scope"] == "cell_ratio"
    assert rows[1]["detector_status"] == "arithmetic_mismatch_candidate"
    assert rows[2]["detector_status"] == "scope_ambiguous"
    assert rows[2]["detector_denominator"] is None
    assert "DETECTOR_DID_NOT_ACCEPT_ARITHMETIC_RELATION" in rows[2]["provenance_flags"]
    role = [fact for fact in rows[1]["denominator_facts"]
            if fact["detector_provenance_role"] == "cell_ratio_denominator"]
    assert len(role) == 1
    assert role[0]["printed_integer"] == 233
    assert role[0]["numeric_equals_detector_base"] is True
    for row in rows:
        for entry in [row["relation_source_anchor"]] + [
            fact["source_anchor"] for fact in row["denominator_facts"]
        ]:
            assert entry["source_sha256"] == sha256(data).hexdigest()
            assert entry["range_semantics"].startswith("original_xml_element")
            assert entry["start_byte"] < entry["end_byte"]
            substring = data[entry["start_byte"]:entry["end_byte"]]
            assert substring.startswith((b"<td", b"<th", b"<p", b"<caption", b"<label"))
            assert entry["source_format"] == "jats_xml"
            assert entry["element_path"].startswith("/article[1]")


def test_arithmetic_is_not_changed_by_a_provenance_trace():
    data = source()
    plain = jats_product.make_report(data, "synthetic", False)
    opt_in = jats_product.make_report(data, "synthetic", False,
                                      include_denominator_trace=True)
    assert "denominator_evidence_trace" not in plain
    assert opt_in["findings"] == plain["findings"]
    assert opt_in["summary"] == plain["summary"]
    assert opt_in["denominator_evidence_trace"]["relation_count"] == len(plain["findings"])


def test_conflicting_denominator_sources_visible_but_not_resolved():
    data = source()
    altered = data.replace(b"Patients, n (%) N=50", b"Patients, n (%) N=20")
    assert altered != data
    trace = traced.trace_denominators(altered)
    row = trace["relations"][0]
    assert row["detector_status"] == "scope_ambiguous"
    assert row["detector_denominator"] is None
    assert row["denominator_fact_values"] == [20, 50]
    assert "MULTIPLE_VISIBLE_DENOMINATOR_VALUES" in row["provenance_flags"]
    assert trace["multiple_fact_values_relation_count"] >= 1


def test_mutated_numeric_detector_result_cannot_fake_source_provenance():
    data = source()
    det = jats.audit_jats_percentage_tables(data)
    det["results"][1]["denominator"] = 999
    with pytest.raises(jats.JATSSourceError, match="NOT_REPLAYED"):
        traced.trace_denominators(data, det)


def test_mutated_evidence_offsets_and_quotes_cannot_fake_source_provenance():
    data = source()
    det = jats.audit_jats_percentage_tables(data)
    if det["results"][1]["evidence"]["denominator_sources"]:
        fact = det["results"][1]["evidence"]["denominator_sources"][0]
        fact["evidence"]["byte_start"] = 1
        with pytest.raises(jats.JATSSourceError, match="NOT_REPLAYED"):
            traced.trace_denominators(data, det)


def test_fact_cap_refuses_instead_of_returning_truncated_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(traced, "MAX_FACTS_PER_RELATION", 0)
    with pytest.raises(jats.JATSSourceError, match="FACT_LIMIT"):
        jats_product.audit_source(FIXTURE, tmp_path / "report", "synthetic",
                                  include_denominator_trace=True)
    assert not (tmp_path / "report").exists()


def test_changed_source_and_report_rehash_do_not_pass_saved_source_replay(tmp_path):
    output = tmp_path / "review"
    original = jats_product.audit_source(
        FIXTURE, output, "synthetic", include_denominator_trace=True,
    )
    assert jats_product.replay_bundle(output, original["manifest_sha256"])["status"] == "verified"
    saved = json.loads((output / "report.json").read_bytes())
    saved["denominator_evidence_trace"]["relations"][1]["detector_denominator"] = 1
    forged = jats_product.canonical_json(saved)
    (output / "report.json").write_bytes(forged)
    manifest = json.loads((output / "manifest.json").read_bytes())
    manifest["files"]["report.json"] = {
        "sha256": jats_product.digest(forged), "bytes": len(forged),
    }
    (output / "manifest.json").write_bytes(jats_product.canonical_json(manifest))
    with pytest.raises(ValueError, match="replay disagrees"):
        jats_product.replay_bundle(output)
    with pytest.raises(ValueError, match="externally pinned hash"):
        jats_product.replay_bundle(output, original["manifest_sha256"])


def test_html_encodes_untrusted_source_content_and_exposes_unresolved_counts(tmp_path):
    source_file = tmp_path / "xml.xml"
    source_file.write_bytes(source().replace(
        b"Direct printed ratio", b"&lt;script&gt;Direct printed ratio&lt;/script&gt;",
    ))
    output = tmp_path / "review"
    jats_product.audit_source(source_file, output, "synthetic",
                              include_denominator_trace=True)
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "denominator trace" in html
    assert "unresolved:" in html
    assert "NOT independent population-scope validation" in html


def test_unsuitable_doctype_does_not_create_bundle(tmp_path):
    source_file = tmp_path / "bad.xml"
    source_file.write_bytes(
        b'<!DOCTYPE article [ <!ENTITY x SYSTEM "file:///private"> ]>'
        b"<article><body><table-wrap>&x;</table-wrap></body></article>"
    )
    output = tmp_path / "review"
    with pytest.raises(ValueError):
        jats_product.audit_source(source_file, output, "synthetic",
                                  include_denominator_trace=True)
    assert not output.exists()


def test_cli_audit_and_replay_work_without_other_optional_modules(tmp_path):
    output = tmp_path / "review"
    cmd = [sys.executable, "-m", "researchwitness", "audit-jats", str(FIXTURE),
           "--document-id", "synthetic", "--output-dir", str(output),
           "--include-denominator-trace"]
    run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=40)
    assert run.returncode == 0, run.stderr
    saved = json.loads((output / "report.json").read_bytes())
    assert saved["denominator_evidence_trace"]["relation_count"] == 3
    assert "table_projection" not in saved
    assert "statistical_se_review" not in saved
    replay = subprocess.run([sys.executable, "-m", "researchwitness", "replay-jats",
                             str(output)], cwd=ROOT, capture_output=True, text=True,
                            timeout=40)
    assert replay.returncode == 0, replay.stderr
