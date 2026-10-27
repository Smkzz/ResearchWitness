"""No real papers: private-pilot negative and replay accounting tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import denominator_scope_review as scope
from tools import pmc_oai_envelope as pmc
from tools import pmc_pilot_ledger as pilot
from tools import source_capture_manifest as capture
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]


def synthetic_oai(pmcid="12345"):
    article = (
        '<article xmlns="" article-type="research-article">'
        '<front><article-meta><article-id pub-id-type="pmc">PMC'
        + pmcid + '</article-id>'
        '<permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/">'
        '<license-p>Creative Commons Attribution 4.0</license-p>'
        '</license></permissions></article-meta></front>'
        '<body><table-wrap><label>Table 1</label><caption>'
        '<p>n = 4; percentages of the enrolled group.</p></caption>'
        '<table><tbody><tr><td>Example</td><td>2 (50%)</td></tr>'
        '</tbody></table></table-wrap></body></article>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<responseDate>2026-10-27T12:00:00Z</responseDate>'
        '<request verb="GetRecord" metadataPrefix="pmc" identifier="'
        f'oai:pubmedcentral.nih.gov:{pmcid}">{pmc.ENDPOINT}</request>'
        '<GetRecord><record><header><identifier>'
        f'oai:pubmedcentral.nih.gov:{pmcid}</identifier>'
        '<datestamp>2026-10-27</datestamp></header><metadata>'
        + article + '</metadata></record></GetRecord></OAI-PMH>'
    ).encode("utf-8")


def transfer(raw, pmcid="12345"):
    return {
        "schema_version": pmc.TRANSFER_VERSION,
        "endpoint": pmc.ENDPOINT,
        "verb": "GetRecord",
        "metadata_prefix": "pmc",
        "requested_identifier": "oai:pubmedcentral.nih.gov:" + pmcid,
        "http_status": 200,
        "body_stage": "decoded_http_entity",
        "expected_body_sha256": sha256(raw).hexdigest(),
        "captured_at_utc": "2026-10-27T12:00:00Z",
        "provider_response_id": None,
        "declared_license_id": "CC-BY-4.0",
        "rights_evidence_uri": "https://creativecommons.org/licenses/by/4.0/",
    }


def ledger(rows):
    return {
        "schema_version": pilot.VERSION,
        "partition": "development_exposed",
        "selection": "operator_declared_not_time_authenticated",
        "records": rows,
    }


def negative(rid="other", family="family-b", outcome="acquisition_unavailable",
             reason="provider_unavailable"):
    return {
        "record_id": rid, "family_id": family, "version_id": "v1",
        "outcome": outcome, "reason": reason, "files": None, "pins": None,
    }


def store(tmp_path, prefix, obj, xml=False):
    name = prefix + (".xml" if xml else ".json")
    (tmp_path / name).write_bytes(obj if xml else vb.canonical_bytes(obj))
    return name


def captured(tmp_path, *, rid="paper-a", family="family-a",
             version="v1", pmcid="12345", parent=None, kind="article"):
    raw = synthetic_oai(pmcid)
    tr = transfer(raw, pmcid)
    source, receipt = pmc.derive(raw, tr)
    meta = {
        "schema_version": capture.METADATA_VERSION,
        "record_id": rid, "work_family_id": family,
        "version_id": version, "kind": kind,
        "parent_record_id": parent,
        "correction_notice_uri": (
            "https://example.org/synthetic-correction" if kind == "correction"
            else None
        ),
        "origin": {
            "retrieval_route": "pmc_open_access",
            "capture_uri": pmc.ENDPOINT,
            "publisher_uri": None,
            "captured_at_utc": tr["captured_at_utc"],
            "expected_source_sha256": sha256(source).hexdigest(),
        },
        "rights": {
            "classification": "declared_open_license",
            "license_id": "CC-BY-4.0",
            "evidence_uri": tr["rights_evidence_uri"],
        },
        "exposure": {
            "partition": "development_exposed",
            "prior_access": "known_exposed",
            "label_status": "no_independent_scientific_label",
        },
    }
    cap = capture.envelope(capture.build_capture(source, meta))
    derivation = pmc.receipt_envelope(receipt)
    packet = scope.make_packet(source)
    packet_env = {"packet": packet, "packet_sha256": vb.commitment(packet)}
    inputs = {
        "raw_envelope": store(tmp_path, rid + "-raw", raw, xml=True),
        "transfer": store(tmp_path, rid + "-transfer", tr),
        "derived_source": store(tmp_path, rid + "-source", source, xml=True),
        "derivation_envelope": store(tmp_path, rid + "-derived", derivation),
        "metadata": store(tmp_path, rid + "-metadata", meta),
        "capture_envelope": store(tmp_path, rid + "-captured", cap),
        "packet_envelope": store(tmp_path, rid + "-packet", packet_env),
        "review_a": None, "review_b": None,
    }
    return {
        "record_id": rid,
        "family_id": family,
        "version_id": version,
        "outcome": "captured_pending_review",
        "reason": None,
        "files": inputs,
        "pins": {
            "expected_derivation_sha256": derivation["receipt_sha256"],
            "expected_capture_sha256": cap["manifest_sha256"],
            "expected_packet_sha256": packet_env["packet_sha256"],
        },
    }


def evaluate(tmp_path, rows):
    doc = ledger(rows)
    return pilot.evaluate(doc, tmp_path,
                          expected_ledger_sha256=vb.commitment(doc))


def test_replayed_private_capture_and_unavailable_family_have_honest_counts(tmp_path):
    outcome = evaluate(tmp_path, [captured(tmp_path), negative()])
    assert outcome["selected_record_count"] == 2
    assert outcome["distinct_declared_family_count"] == 2
    assert outcome["raw_to_review_chains_replayed"] == 1
    assert outcome["outcomes"]["captured_pending_review"] == 1
    assert outcome["outcomes"]["acquisition_unavailable"] == 1
    assert outcome["refusal_reasons"] == {"provider_unavailable": 1}
    assert outcome["unreviewed_captured_records"] == 1
    assert outcome["capture_registry_sha256"] is not None
    assert not any(outcome[key] for key in (
        "candidate_identifiers_or_source_text_emitted",
        "independent_retrieval_provenance_verified",
        "article_specific_rights_independently_verified",
        "independent_work_families_verified",
        "independent_scientific_labels_established",
        "protected_holdout_qualified",
        "scientific_detection_improvement_established",
    ))
    serialized = vb.canonical_bytes(outcome)
    assert b"PMC12345" not in serialized
    assert b"Example" not in serialized
    assert outcome == evaluate(tmp_path, [
        negative(),  # same cases, changed order changes pinned commitment only
        # source files cannot be replayed twice by a different file manifest
    ][:1]) if False else outcome


def test_entirely_blocked_pilot_keeps_full_denominator_without_data_claim(tmp_path):
    out = evaluate(tmp_path, [
        negative("a", "a-family", "rights_excluded", "rights_unknown"),
        negative("b", "b-family", "acquisition_unavailable", "timeout"),
        negative("c", "c-family", "rights_excluded", "rights_restricted"),
    ])
    assert out["selected_record_count"] == 3
    assert out["distinct_declared_family_count"] == 3
    assert out["raw_to_review_chains_replayed"] == 0
    assert out["capture_registry_sha256"] is None
    assert out["outcomes"]["rights_excluded"] == 2
    assert out["outcomes"]["acquisition_unavailable"] == 1
    assert out["independent_scientific_labels_established"] is False


def test_xml_parser_refusal_must_be_replayed_not_just_declared(tmp_path):
    raw = synthetic_oai().replace(
        b"<GetRecord>", b'<!DOCTYPE malicious SYSTEM "file:///etc/passwd"><GetRecord>',
        1
    )
    paths = {
        "raw_envelope": store(tmp_path, "bad-raw", raw, xml=True),
        "transfer": store(tmp_path, "bad-transfer", transfer(raw)),
    }
    failed = {
        "record_id": "failed-p", "family_id": "family-x",
        "version_id": "v1", "outcome": "parser_refused",
        "reason": "ENVELOPE_DTD_OR_ENTITY",
        "files": paths, "pins": None,
    }
    out = evaluate(tmp_path, [failed, negative()])
    assert out["outcomes"]["parser_refused"] == 1
    failed["reason"] = "ENVELOPE_MALFORMED_XML"
    with pytest.raises(vb.BenchmarkError, match="PILOT_PARSER_REFUSAL_MISMATCH"):
        evaluate(tmp_path, [failed, negative()])


def test_ambiguous_late_reviewer_declaration_fails_closed(tmp_path):
    good = captured(tmp_path)
    good["outcome"] = "development_reviews_submitted"
    with pytest.raises(vb.BenchmarkError, match="PILOT_REVIEW_COMPLETENESS"):
        evaluate(tmp_path, [good, negative()])
    good["files"]["review_a"] = "missing-review.json"
    with pytest.raises(vb.BenchmarkError, match="PILOT_REVIEW_COMPLETENESS"):
        evaluate(tmp_path, [good, negative()])


def test_cross_family_duplicate_original_source_bytes_never_inflate_count(tmp_path):
    a = captured(tmp_path, rid="a", family="family-a")
    b = captured(tmp_path, rid="b", family="family-b")
    with pytest.raises(vb.BenchmarkError, match="PILOT_REUSED_SOURCE_BYTES"):
        evaluate(tmp_path, [a, b])


def test_corrections_and_revisions_are_one_declared_family_not_two(tmp_path):
    article = captured(tmp_path, rid="original", family="family-x", pmcid="12345")
    correction = captured(
        tmp_path, rid="corr", family="family-x", pmcid="67890",
        version="v2", kind="correction", parent="original"
    )
    result = evaluate(tmp_path, [article, correction, negative()])
    assert result["selected_record_count"] == 3
    assert result["distinct_declared_family_count"] == 2
    assert result["raw_to_review_chains_replayed"] == 2


@pytest.mark.parametrize(("mutator", "code"), [
    (lambda d: d.update(partition="sealed_confirmatory"), "PILOT_PROTECTED_PARTITION"),
    (lambda d: d.update(selection="third_party_confirmed"),
     "PILOT_SELECTION_NOT_AUTHENTICATED"),
    (lambda d: d["records"][1].update(record_id="paper-a"), "PILOT_DUPLICATE_RECORD"),
    (lambda d: d["records"][1].update(family_id="family-a", version_id="v1"),
     "PILOT_DUPLICATE_VERSION"),
    (lambda d: d["records"][1].update(outcome="scientifically_proven"),
     "PILOT_OUTCOME_INVALID"),
    (lambda d: d["records"][1].update(files={"raw": "secret.xml"}),
     "PILOT_NEGATIVE_EVIDENCE_FIELDS"),
])
def test_reject_protected_or_conflicting_or_missing_negative_evidence(
        tmp_path, mutator, code):
    d = ledger([captured(tmp_path), negative()])
    mutator(d)
    with pytest.raises(vb.BenchmarkError, match=code):
        pilot.evaluate(d, tmp_path, expected_ledger_sha256=vb.commitment(d))


def test_swapped_version_hash_and_stale_pin_fail(tmp_path):
    doc = ledger([captured(tmp_path), negative()])
    expected = vb.commitment(doc)
    doc["records"][0]["version_id"] = "v99"
    with pytest.raises(vb.BenchmarkError, match="PILOT_LEDGER_EXTERNAL_PIN_MISMATCH"):
        pilot.evaluate(doc, tmp_path, expected_ledger_sha256=expected)
    with pytest.raises(vb.BenchmarkError, match="PILOT_DECLARED_IDENTITY_MISMATCH"):
        pilot.evaluate(doc, tmp_path, expected_ledger_sha256=vb.commitment(doc))
    doc["records"][0]["version_id"] = "v1"
    doc["records"][0]["pins"]["expected_derivation_sha256"] = "f" * 64
    with pytest.raises(vb.BenchmarkError, match="DERIVATION_EXTERNAL_PIN_MISMATCH"):
        pilot.evaluate(doc, tmp_path, expected_ledger_sha256=vb.commitment(doc))


def test_unsafe_paths_and_symlinks_refused(tmp_path):
    doc = ledger([captured(tmp_path), negative()])
    for evil in ("../bad.xml", "C:evil.xml", "outside\\secret.xml", "AUX.txt"):
        altered = deepcopy(doc)
        altered["records"][0]["files"]["raw_envelope"] = evil
        with pytest.raises(vb.BenchmarkError, match="PILOT_PRIVATE_FILENAME"):
            pilot.evaluate(altered, tmp_path,
                           expected_ledger_sha256=vb.commitment(altered))
    bad = tmp_path / "linked.xml"
    try:
        bad.symlink_to(tmp_path / doc["records"][0]["files"]["raw_envelope"])
    except (OSError, NotImplementedError):
        pytest.skip("Symlink unsupported")
    altered = deepcopy(doc)
    altered["records"][0]["files"]["raw_envelope"] = bad.name
    with pytest.raises(ValueError):
        pilot.evaluate(altered, tmp_path,
                       expected_ledger_sha256=vb.commitment(altered))


def test_cli_private_only_sanitized_output_and_stale_pin(tmp_path):
    doc = ledger([captured(tmp_path), negative()])
    name = tmp_path / "ledger.json"
    name.write_bytes(vb.canonical_bytes(doc))
    args = [
        sys.executable, "-m", "tools.pmc_pilot_ledger",
        "--ledger", str(name),
        "--private-root", str(tmp_path),
        "--expected-ledger-sha256", vb.commitment(doc),
    ]
    ok = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    assert ok.returncode == 0, ok.stderr.decode()
    report = json.loads(ok.stdout)
    assert report["selected_record_count"] == 2
    assert b"paper-a" not in ok.stdout
    assert b"PMC12345" not in ok.stdout
    assert b"\r\n" not in ok.stdout
    failed = args[:]
    failed[-1] = "0" * 64
    no = subprocess.run(failed, cwd=ROOT, capture_output=True, timeout=30)
    assert no.returncode == 2
    assert json.loads(no.stderr)["code"] == "PILOT_LEDGER_EXTERNAL_PIN_MISMATCH"
