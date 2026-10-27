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
from tools import pmc_pilot_selection_frame as selection
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
    assert outcome["scientific_detection_improvement_established"] is False


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


def selected_frame(tmp_path, rows):
    """Invented frame: the live protocol requires an externally held prior pin."""
    registered = []
    for number, row in enumerate(rows):
        files = row["files"]
        if files is not None and "transfer" in files:
            request = vb.parse_document((tmp_path / files["transfer"]).read_bytes())
            oai = request["requested_identifier"]
        else:
            oai = "oai:pubmedcentral.nih.gov:" + str(90001 + number)
        if files is not None and "metadata" in files:
            metadata = vb.parse_document((tmp_path / files["metadata"]).read_bytes())
            kind = metadata["kind"]
            parent = metadata["parent_record_id"]
        else:
            kind, parent = "article", None
        registered.append({
            "record_id": row["record_id"],
            "family_id": row["family_id"],
            "version_id": row["version_id"],
            "oai_identifier": oai,
            "kind": kind,
            "parent_record_id": parent,
        })
    return {
        "schema_version": selection.VERSION,
        "partition": "development_exposed",
        "selection": "operator_declared_not_time_authenticated",
        "records": registered,
    }


def framed(tmp_path, rows, frame=None):
    if frame is None:
        frame = selected_frame(tmp_path, rows)
    value = ledger(rows)
    return pilot.evaluate(
        value, tmp_path, expected_ledger_sha256=vb.commitment(value),
        selection_frame=frame, expected_frame_sha256=vb.commitment(frame),
    )


def test_framed_report_accounts_for_explicitly_unattempted_sources(tmp_path):
    pending = negative("pending", "family-c")
    pending.update(outcome="not_attempted", reason=None)
    result = framed(tmp_path, [captured(tmp_path), negative(), pending])
    assert result["schema_version"] == "rw-private-pmc-development-pilot-report.v2"
    assert result["selected_record_count"] == 3
    assert result["raw_to_review_chains_replayed"] == 1
    assert result["outcomes"]["not_attempted"] == 1
    assert result["selected_attempts_not_yet_run"] == 1
    assert result["selected_attempts_with_declared_outcomes"] == 2
    assert result["selection_frame_coverage"] == "all_selected_record_ids_accounted"
    assert result["pre_outcome_frame_timing_authenticated"] is False
    assert result["independent_scientific_labels_established"] is False
    assert b"PMC12345" not in vb.canonical_bytes(result)


def test_v1_selection_can_shrink_but_framed_selection_cannot(tmp_path):
    rows = [
        captured(tmp_path),
        negative("second", "family-b"),
        negative("third", "family-c"),
    ]
    frozen = selected_frame(tmp_path, rows)
    assert evaluate(tmp_path, rows[:2])["selected_record_count"] == 2
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_COVERAGE_MISMATCH"):
        framed(tmp_path, rows[:2], frozen)


def test_pinned_frame_rejects_modified_and_recommitted_source_id(tmp_path):
    rows = [captured(tmp_path), negative()]
    declared = selected_frame(tmp_path, rows)
    old = vb.commitment(declared)
    declared["records"][0]["oai_identifier"] = "oai:pubmedcentral.nih.gov:43210"
    doc = ledger(rows)
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_EXTERNAL_PIN_MISMATCH"):
        pilot.evaluate(
            doc, tmp_path, expected_ledger_sha256=vb.commitment(doc),
            selection_frame=declared, expected_frame_sha256=old,
        )
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_OAI_IDENTITY_MISMATCH"):
        framed(tmp_path, rows, declared)


def test_frame_lineage_must_match_source_capture(tmp_path):
    rows = [
        captured(tmp_path, rid="original", family="family-a", pmcid="12345"),
        captured(tmp_path, rid="corr", family="family-a", pmcid="67890",
                 version="v2", kind="correction", parent="original"),
        negative(),
    ]
    frame = selected_frame(tmp_path, rows)
    assert framed(tmp_path, rows, frame)["raw_to_review_chains_replayed"] == 2
    frame["records"][1]["kind"] = "supplement"
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_SOURCE_LINEAGE_MISMATCH"):
        framed(tmp_path, rows, frame)


def test_frame_cannot_share_pmc_id_across_declared_families(tmp_path):
    rows = [negative("a", "fa"), negative("b", "fb")]
    frame = selected_frame(tmp_path, rows)
    frame["records"][1]["oai_identifier"] = frame["records"][0]["oai_identifier"]
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_SOURCE_CROSSES_FAMILIES"):
        framed(tmp_path, rows, frame)


def test_selection_cycles_and_missing_parents_are_refused(tmp_path):
    rows = [negative("a", "fa"), negative("b", "fa"), negative("c", "fb")]
    frame = selected_frame(tmp_path, rows)
    frame["records"][1].update(
        kind="revision", parent_record_id="a",
        oai_identifier=frame["records"][0]["oai_identifier"],
    )
    assert len(selection.validate(
        frame, expected_frame_sha256=vb.commitment(frame)
    )) == 3
    frame["records"][0].update(kind="revision", parent_record_id="b")
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_LINEAGE_CYCLE"):
        selection.validate(frame, expected_frame_sha256=vb.commitment(frame))
    frame["records"][0]["parent_record_id"] = "not-selected"
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_PARENT_NOT_SELECTED"):
        selection.validate(frame, expected_frame_sha256=vb.commitment(frame))


def test_not_attempted_cannot_claim_error_or_files(tmp_path):
    row = negative("a", "fa")
    row.update(outcome="not_attempted", reason=None)
    assert framed(tmp_path, [row, negative("b", "fb")])[
        "selected_attempts_not_yet_run"
    ] == 1
    row["reason"] = "timeout"
    with pytest.raises(vb.BenchmarkError, match="PILOT_NOT_ATTEMPTED_FIELDS"):
        framed(tmp_path, [row, negative("b", "fb")])


def test_private_frame_rejects_protected_and_unsupported_authority_claims(tmp_path):
    rows = [negative("a", "fa"), negative("b", "fb")]
    frame = selected_frame(tmp_path, rows)
    frame["partition"] = "sealed"
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_PROTECTED_PARTITION"):
        framed(tmp_path, rows, frame)
    frame["partition"] = "development_exposed"
    frame["pre_outcome_registered"] = True
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_FIELDS"):
        framed(tmp_path, rows, frame)


def test_framed_parser_refusal_checks_preselected_oai_id(tmp_path):
    raw = synthetic_oai().replace(
        b"<GetRecord>", b'<!DOCTYPE unsafe SYSTEM "file:///etc/passwd"><GetRecord>',
        1,
    )
    row = {
        "record_id": "bad-source", "family_id": "family-one",
        "version_id": "v1", "outcome": "parser_refused",
        "reason": "ENVELOPE_DTD_OR_ENTITY",
        "files": {
            "raw_envelope": store(tmp_path, "bad-original", raw, xml=True),
            "transfer": store(tmp_path, "bad-transfer-file", transfer(raw)),
        }, "pins": None,
    }
    records = [row, negative()]
    frame = selected_frame(tmp_path, records)
    assert framed(tmp_path, records, frame)["outcomes"]["parser_refused"] == 1
    frame["records"][0]["oai_identifier"] = "oai:pubmedcentral.nih.gov:98765"
    with pytest.raises(vb.BenchmarkError, match="PILOT_FRAME_OAI_IDENTITY_MISMATCH"):
        framed(tmp_path, records, frame)


def test_new_framed_cli_and_external_pins(tmp_path):
    rows = [captured(tmp_path), negative()]
    frame = selected_frame(tmp_path, rows)
    doc = ledger(rows)
    f = tmp_path / "selected-frame.json"
    l = tmp_path / "attempts.json"
    f.write_bytes(vb.canonical_bytes(frame))
    l.write_bytes(vb.canonical_bytes(doc))
    command = [
        sys.executable, "-m", "tools.pmc_pilot_selection_frame",
        "--frame", str(f), "--expected-frame-sha256", vb.commitment(frame),
        "--ledger", str(l), "--private-root", str(tmp_path),
        "--expected-ledger-sha256", vb.commitment(doc),
    ]
    ok = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
    assert ok.returncode == 0, ok.stderr
    assert b"\r\n" not in ok.stdout
    assert json.loads(ok.stdout)["selection_frame_coverage"] == (
        "all_selected_record_ids_accounted"
    )
    assert b"PMC12345" not in ok.stdout
    bad = command[:]
    bad[bad.index("--expected-frame-sha256") + 1] = "f" * 64
    refused = subprocess.run(bad, cwd=ROOT, capture_output=True, timeout=30)
    assert refused.returncode == 2
    assert json.loads(refused.stderr)["code"] == "PILOT_FRAME_EXTERNAL_PIN_MISMATCH"
