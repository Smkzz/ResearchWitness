"""Synthetic offline original-OAI-to-JATS integration. Not a real source test."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from researchwitness import jats_product
from tools import pmc_oai_envelope as pmc
from tools import pmc_oai_jats_pilot as pilot
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]


def fixture(tmp_path: Path, number: str = "12345"):
    article = (ROOT / "examples" / "synthetic-jats" / "article.xml").read_text("utf-8")
    article = article.split("\n", 1)[1]
    article = article.replace("<article>", '<article xmlns="" article-type="research-article">', 1)
    article = article.replace(
        "<article-meta>",
        '<article-meta><article-id pub-id-type="pmc">PMC' + number + '</article-id>'
        '<permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/">'
        '<license-p>Creative Commons Attribution 4.0</license-p>'
        '</license></permissions>', 1,
    )
    raw = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<responseDate>2026-11-04T15:00:00Z</responseDate>'
        '<request verb="GetRecord" metadataPrefix="pmc" '
        f'identifier="oai:pubmedcentral.nih.gov:{number}">{pmc.ENDPOINT}</request>'
        '<GetRecord><record><header>'
        f'<identifier>oai:pubmedcentral.nih.gov:{number}</identifier>'
        '<datestamp>2026-11-01</datestamp></header><metadata>'
        + article + '</metadata></record></GetRecord></OAI-PMH>'
    ).encode("utf-8")
    transfer = {
        "schema_version": pmc.TRANSFER_VERSION,
        "endpoint": pmc.ENDPOINT,
        "verb": "GetRecord", "metadata_prefix": "pmc",
        "requested_identifier": f"oai:pubmedcentral.nih.gov:{number}",
        "http_status": 200,
        "body_stage": "decoded_http_entity",
        "expected_body_sha256": sha256(raw).hexdigest(),
        "captured_at_utc": "2026-11-04T15:01:00Z",
        "provider_response_id": None,
        "declared_license_id": "CC-BY-4.0",
        "rights_evidence_uri": "https://creativecommons.org/licenses/by/4.0/",
    }
    rawfile, transf = tmp_path / "oai.xml", tmp_path / "transfer.json"
    rawfile.write_bytes(raw)
    transf.write_bytes(vb.canonical_bytes(transfer))
    return rawfile, transf, raw, transfer


def execute(tmp_path: Path, *, trace=False, structure=False):
    rawfile, transfer, raw, declaration = fixture(tmp_path)
    out = tmp_path / "pilot"
    result = pilot.run(rawfile, transfer, out,
                       expected_raw_sha256=sha256(raw).hexdigest(),
                       document_id="PMC12345", include_denominator_trace=trace,
                       include_structure=structure)
    return result, out, raw, declaration


def test_exact_full_source_derivation_audit_and_second_replay(tmp_path):
    result, out, raw, _ = execute(tmp_path)
    assert result["status"] == "OFFLINE_SOURCE_DERIVED_AND_JATS_REPLAYED"
    assert result["raw_envelope_sha256"] == sha256(raw).hexdigest()
    assert (out / "original-oai-response.xml").read_bytes() == raw
    assert (out / "derived-article.xml").read_bytes().startswith(b"<article")
    assert result["original_article_span"]["byte_end_exclusive"] <= len(raw)
    assert result["derived_jats_sha256"] == sha256((out / "derived-article.xml").read_bytes()).hexdigest()
    assert result["jats_replay_status"] == "verified"
    assert result["source_linked_results"]["arithmetic_matches"] == 1
    assert result["source_linked_results"]["mismatch_candidates"] == 1
    assert result["source_linked_results"]["abstentions"] == 1
    assert result["tables_inspected"] == 2
    assert jats_product.replay_bundle(out / "jats-audit", result["jats_audit_manifest_sha256"])["status"] == "verified"
    assert not result["source_origin_authenticated"]
    assert not result["rights_independently_verified"]
    assert not result["source_interpretation_independently_reviewed"]
    assert not result["scientific_accuracy_established"]
    assert not result["paper_error_established"]
    assert result["no_network_used"] is True
    assert "Invented software fixture" not in json.dumps(result)
    assert vb.parse_document((out / "result.json").read_bytes()) == result
    assert not (out / "jats-audit" / "report.json").read_bytes().startswith(b"<")


def test_optional_context_features_still_replay(tmp_path):
    result, out, *_ = execute(tmp_path, trace=True, structure=True)
    saved = jats_product.strict_json((out / "jats-audit" / "report.json").read_bytes())
    assert "denominator_evidence_trace" in saved
    assert "table_projection" in saved
    assert jats_product.replay_bundle(out / "jats-audit", result["jats_audit_manifest_sha256"])["status"] == "verified"


@pytest.mark.parametrize("mutation,code", [
    ("wrong_outer_pin", "EXTERNAL_RAW_PIN_MISMATCH"),
    ("wrong_docid", "DOCUMENT_ID_TRANSFER_MISMATCH"),
    ("wrong_transfer_hash", "TRANSFER_BODY_HASH_MISMATCH"),
    ("wrong_license", "ARTICLE_LICENSE_UNCLEAR"),
    ("wrong_status", "PROVIDER_RESPONSE_NOT_SUCCESSFUL"),
    ("not_oai", "ENVELOPE_NOT_OAI_PMH"),
    ("bad_source", "ENVELOPE_MALFORMED_XML"),
])
def test_bad_identity_or_semantics_never_get_a_success_receipt(tmp_path, mutation, code):
    rawfile, transfer_file, raw, declaration = fixture(tmp_path)
    pin, document_id = sha256(raw).hexdigest(), "PMC12345"
    if mutation == "wrong_outer_pin":
        pin = "0" * 64
    elif mutation == "wrong_docid":
        document_id = "PMC55555"
    elif mutation == "wrong_transfer_hash":
        declaration["expected_body_sha256"] = "a" * 64
    elif mutation == "wrong_license":
        declaration["declared_license_id"] = "CC0-1.0"
    elif mutation == "wrong_status":
        declaration["http_status"] = 404
    elif mutation == "not_oai":
        raw = (ROOT / "examples" / "synthetic-jats" / "article.xml").read_bytes()
        rawfile.write_bytes(raw)
        declaration["expected_body_sha256"] = sha256(raw).hexdigest()
        pin = sha256(raw).hexdigest()
    elif mutation == "bad_source":
        raw = raw.replace(b"</OAI-PMH>", b"</WHOOPS>")
        rawfile.write_bytes(raw)
        declaration["expected_body_sha256"] = sha256(raw).hexdigest()
        pin = sha256(raw).hexdigest()
    transfer_file.write_bytes(vb.canonical_bytes(declaration))
    with pytest.raises(vb.BenchmarkError, match=code):
        pilot.run(rawfile, transfer_file, tmp_path / "pilot", expected_raw_sha256=pin,
                  document_id=document_id)
    assert not (tmp_path / "pilot").exists()


def test_output_is_exclusive_and_replay_tamper_is_not_accepted(tmp_path):
    result, out, raw, _ = execute(tmp_path)
    with pytest.raises(vb.BenchmarkError, match="OUTPUT_MUST_BE_FRESH"):
        pilot.run(tmp_path / "oai.xml", tmp_path / "transfer.json", out,
                  expected_raw_sha256=sha256(raw).hexdigest(),document_id="PMC12345")
    source = out / "jats-audit" / "source.xml"
    source.write_bytes(source.read_bytes().replace(b"4 (8.10)", b"4 (8.00)"))
    with pytest.raises(ValueError):
        jats_product.replay_bundle(out / "jats-audit", result["jats_audit_manifest_sha256"])


def test_cli_is_bounded_and_emits_no_raw_text(tmp_path, capsys):
    rawfile, trans, raw, _ = fixture(tmp_path)
    assert pilot.main(["--raw-envelope", str(rawfile), "--transfer", str(trans),
                       "--expected-raw-sha256", sha256(raw).hexdigest(),
                       "--document-id", "PMC12345", "--output-dir", str(tmp_path / "cli")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_linked_results"]["mismatch_candidates"] == 1
    assert "Invented software fixture" not in json.dumps(result)
    assert pilot.main(["--raw-envelope", str(rawfile), "--transfer", str(trans),
                       "--expected-raw-sha256", "0" * 64,
                       "--document-id", "PMC12345", "--output-dir", str(tmp_path / "wrong")]) == 2
    captured=capsys.readouterr()
    assert "EXTERNAL_RAW_PIN_MISMATCH" in captured.err and not captured.out
    assert not (tmp_path / "wrong").exists()


def test_transit_links_and_duplicate_declarations_are_rejected(tmp_path):
    raw_file, transfer_file, raw, _ = fixture(tmp_path)
    alias = tmp_path / "raw-symlink.xml"
    try:
        alias.symlink_to(raw_file)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises((vb.BenchmarkError, ValueError, OSError)):
        pilot.run(alias, transfer_file, tmp_path / "disallowed",
                  expected_raw_sha256=sha256(raw).hexdigest(), document_id="PMC12345")
    assert not (tmp_path / "disallowed").exists()
    alias.unlink()
    # A structurally valid checksum cannot restore duplicate decoded JSON keys.
    declaration=transfer_file.read_bytes()
    duplicate=declaration.replace(b'"http_status":200',b'"http_status":200,"http_status":200')
    assert duplicate != declaration
    transfer_file.write_bytes(duplicate)
    with pytest.raises(vb.BenchmarkError):
        pilot.run(raw_file, transfer_file, tmp_path / "duplicate",
                  expected_raw_sha256=sha256(raw).hexdigest(), document_id="PMC12345")
    assert not (tmp_path / "duplicate").exists()


def test_wrong_report_source_pin_fails_before_creating_output(tmp_path):
    raw_file, transfer_file, raw, _ = fixture(tmp_path)
    for bad in (True, "ABC", "z"*64):
        with pytest.raises(vb.BenchmarkError, match="EXPECTED_RAW_PIN_INVALID"):
            pilot.run(raw_file, transfer_file, tmp_path / "bad-source-pin",
                      expected_raw_sha256=bad, document_id="PMC12345")
    assert not (tmp_path / "bad-source-pin").exists()


def test_report_is_final_success_receipt_not_a_partial_directory(tmp_path, monkeypatch):
    rawfile, transfer, raw, _ = fixture(tmp_path)

    def fail_during_audit(*_args, **_kwargs):
        raise ValueError("SYNTHETIC_INTERRUPTED_AUDIT")

    monkeypatch.setattr(jats_product, "audit_source", fail_during_audit)
    out = tmp_path / "interrupted"
    with pytest.raises(ValueError, match="SYNTHETIC_INTERRUPTED_AUDIT"):
        pilot.run(rawfile, transfer, out,
                  expected_raw_sha256=sha256(raw).hexdigest(), document_id="PMC12345")
    # An incomplete private directory must never contain an accepted result.json.
    assert out.is_dir()
    assert not (out / "result.json").exists()
    with pytest.raises(vb.BenchmarkError, match="OUTPUT_MUST_BE_FRESH"):
        pilot.run(rawfile, transfer, out,
                  expected_raw_sha256=sha256(raw).hexdigest(), document_id="PMC12345")


def test_second_parse_summary_must_match_pinned_first_parse(tmp_path, monkeypatch):
    rawfile, transfer, raw, _ = fixture(tmp_path)
    actual = jats_product.audit_source

    def changed_summary(*args, **kwargs):
        result = actual(*args, **kwargs)
        result["summary"]["mismatch_candidates"] += 1
        return result

    monkeypatch.setattr(jats_product, "audit_source", changed_summary)
    out = tmp_path / "drifted"
    with pytest.raises(vb.BenchmarkError, match="AUDIT_RECOMPUTATION_MISMATCH"):
        pilot.run(rawfile, transfer, out,
                  expected_raw_sha256=sha256(raw).hexdigest(), document_id="PMC12345")
    assert out.is_dir() and not (out / "result.json").exists()


def test_accepted_receipt_has_explicit_feature_flags_and_no_private_path(tmp_path):
    result, out, *_ = execute(tmp_path, trace=True, structure=True)
    assert result["analyzed_features"] == {
        "include_structure": True, "include_denominator_trace": True,
    }
    assert "private_output_dir" not in result
    assert str(out) not in json.dumps(result)
    assert result["source_origin_authenticated"] is False
    assert result["rights_independently_verified"] is False
    assert result["paper_error_established"] is False


def test_hardlinked_input_rejected_before_creating_output(tmp_path):
    import os
    rawfile, transfer, raw, _ = fixture(tmp_path)
    hardlink = tmp_path / "second-name.xml"
    try:
        os.link(rawfile, hardlink)
    except (OSError, NotImplementedError):
        pytest.skip("hardlink unavailable")
    with pytest.raises((vb.BenchmarkError, OSError, ValueError)):
        pilot.run(rawfile, transfer, tmp_path / "no-hardlink",
                  expected_raw_sha256=sha256(raw).hexdigest(), document_id="PMC12345")
    assert not (tmp_path / "no-hardlink").exists()
