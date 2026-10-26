"""Synthetic PMC OAI-PMH capture derivation tests; no real sources or auth claims."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools import pmc_oai_envelope as pmc
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]


def example(*, identifier="12345", article_id=None, license_href=None,
            inherit_xlink=True, article_ns="", article_type="research-article",
            extra_article_id="", inside_article="") -> bytes:
    article_id = article_id or "PMC" + identifier
    license_href = license_href or pmc.LICENCE_HREF["CC-BY-4.0"]
    declared_xlink = "" if inherit_xlink else ' xmlns:xlink="http://www.w3.org/1999/xlink"'
    article = (
        f'<article xmlns="{article_ns}"{declared_xlink} article-type="{article_type}">'
        '<front><article-meta>'
        f'<article-id pub-id-type="pmc">{article_id}</article-id>{extra_article_id}'
        f'<permissions><license xlink:href="{license_href}">'
        '<license-p>Creative Commons Attribution 4.0</license-p></license>'
        '</permissions></article-meta></front><body><sec><p>'
        f'Invented example 2 (50%) &amp; no real paper. {inside_article}'
        '</p></sec></body></article>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<responseDate>2026-10-26T20:20:00Z</responseDate>'
        f'<request verb="GetRecord" metadataPrefix="pmc" '
        f'identifier="oai:pubmedcentral.nih.gov:{identifier}">{pmc.ENDPOINT}</request>'
        '<GetRecord><record><header>'
        f'<identifier>oai:pubmedcentral.nih.gov:{identifier}</identifier>'
        '<datestamp>2026-10-20</datestamp></header><metadata>'
        + article + '</metadata></record></GetRecord></OAI-PMH>'
    ).encode("utf-8")


def transfer(raw: bytes, *, identifier="12345") -> dict:
    return {
        "schema_version": pmc.TRANSFER_VERSION,
        "endpoint": pmc.ENDPOINT,
        "verb": "GetRecord",
        "metadata_prefix": "pmc",
        "requested_identifier": f"oai:pubmedcentral.nih.gov:{identifier}",
        "http_status": 200,
        "body_stage": "decoded_http_entity",
        "expected_body_sha256": sha256(raw).hexdigest(),
        "captured_at_utc": "2026-10-26T20:21:00Z",
        "provider_response_id": None,
        "declared_license_id": "CC-BY-4.0",
        "rights_evidence_uri": "https://creativecommons.org/licenses/by/4.0/",
    }


def test_exact_envelope_identity_and_deterministic_inherited_namespace_bridge():
    raw = example()
    source, record = pmc.derive(raw, transfer(raw))
    embedded = raw[record["original_article_span"]["byte_start"]:
                   record["original_article_span"]["byte_end_exclusive"]]
    assert b'xmlns:xlink="http://www.w3.org/1999/xlink"' in source
    assert record["namespace_declarations_inserted"] == 1
    assert record["derived_equals_original_article_span"] is False
    assert record["derived_is_full_provider_response"] is False
    assert record["original_article_span"]["sha256"] == sha256(embedded).hexdigest()
    assert record["derived_jats_sha256"] == sha256(source).hexdigest()
    assert record["raw_envelope_sha256"] == sha256(raw).hexdigest()
    assert record["status"] == "OFFLINE_DEVELOPMENT_DERIVATION_ONLY"
    assert not any(record[k] for k in ("publisher_authenticity_verified",
                                     "license_rights_verified_by_tool",
                                     "scientific_labels_established",
                                     "protected_custody_qualified"))
    assert b"Invented example" in source
    assert "Invented example" not in json.dumps(pmc.receipt_envelope(record))
    assert pmc.derive(raw, deepcopy(transfer(raw))) == (source, record)


def test_local_namespace_needs_no_transformation():
    raw = example(inherit_xlink=False)
    source, record = pmc.derive(raw, transfer(raw))
    assert record["namespace_declarations_inserted"] == 0
    assert record["derived_equals_original_article_span"] is True
    assert source == raw[record["original_article_span"]["byte_start"]:
                         record["original_article_span"]["byte_end_exclusive"]]


def test_allowed_explicit_jats_namespace_is_preserved():
    raw = example(article_ns="http://jats.nlm.nih.gov")
    source, record = pmc.derive(raw, transfer(raw))
    assert source.startswith(b'<article xmlns="http://jats.nlm.nih.gov"')
    assert record["derived_jats_sha256"] == sha256(source).hexdigest()


def test_external_pin_replay_catches_mutated_source_record_and_claims():
    raw = example()
    source, record = pmc.derive(raw, transfer(raw))
    envelope = pmc.receipt_envelope(record)
    pin = envelope["receipt_sha256"]
    assert pmc.replay(raw, transfer(raw), source, envelope,
                      expected_receipt_sha256=pin)["status"] == (
                          "RAW_SPAN_AND_DERIVED_JATS_REPLAYED")
    with pytest.raises(vb.BenchmarkError, match="DERIVATION_REPLAY_MISMATCH"):
        pmc.replay(raw, transfer(raw), source + b" ", envelope,
                   expected_receipt_sha256=pin)
    altered = deepcopy(envelope)
    altered["receipt"]["license_rights_verified_by_tool"] = True
    altered["receipt_sha256"] = vb.commitment(altered["receipt"])
    with pytest.raises(vb.BenchmarkError, match="DERIVATION_EXTERNAL_PIN_MISMATCH"):
        pmc.replay(raw, transfer(raw), source, altered, expected_receipt_sha256=pin)
    with pytest.raises(vb.BenchmarkError, match="DERIVATION_EXTERNAL_PIN_MISMATCH"):
        pmc.replay(raw, transfer(raw), source, envelope,
                   expected_receipt_sha256="0" * 64)


@pytest.mark.parametrize(("change", "expected"), [
    (lambda b: b.replace(b"PMC12345", b"PMC99999"), "ARTICLE_PMC_ID_MISMATCH"),
    (lambda b: b.replace(b"<article-id", b"<article-id", 1).replace(
        b"</article-id>", b'</article-id><article-id pub-id-type="pmc">PMC12345</article-id>', 1),
     "ARTICLE_PMC_ID_COUNT"),
    (lambda b: b.replace(b"by/4.0/", b"by/3.0/"), "ARTICLE_LICENSE_UNCLEAR"),
    (lambda b: b.replace(b"research-article", b"correction"), "ARTICLE_KIND_UNSUPPORTED"),
    (lambda b: b.replace(b"Creative Commons Attribution 4.0", b"All rights reserved"), "ARTICLE_LICENSE_CONTRADICTORY"),
    (lambda b: b.replace(b"<article xmlns=\"\"", b"<article"), "ARTICLE_NAMESPACE_UNSUPPORTED"),
    (lambda b: b.replace(b"2026-10-20</datestamp>", b"2026-99-20</datestamp>"), "OAI_DATESTAMP_INVALID"),
    (lambda b: b.replace(b"identifier=\"oai:pubmedcentral.nih.gov:12345\"",
                         b"identifier=\"oai:pubmedcentral.nih.gov:77777\""), "OAI_REQUEST_MISMATCH"),
    (lambda b: b.replace(b"<metadata>", b"<metadata><article/>", 1), "OAI_MULTIPLE_ARTICLES"),
    (lambda b: b.replace(b"<header>", b"<header status=\"deleted\">", 1), "OAI_DELETED_RECORD"),
    (lambda b: b.replace(b"<GetRecord>", b"<GetRecord><record/>", 1), "OAI_RECORD_COUNT"),
    (lambda b: b.replace(b"<body>", b"<body><xi:include xmlns:xi=\"http://www.w3.org/2001/XInclude\" href=\"file:///etc/passwd\"/>", 1), "ENVELOPE_XINCLUDE_FORBIDDEN"),
])
def test_synthetic_source_ambiguity_refused(change, expected):
    raw = change(example())
    with pytest.raises(vb.BenchmarkError, match=expected):
        pmc.derive(raw, transfer(raw))


@pytest.mark.parametrize(("change", "expected"), [
    (lambda d: d.update(http_status=503), "PROVIDER_RESPONSE_NOT_SUCCESSFUL"),
    (lambda d: d.update(body_stage="wire_compressed"), "TRANSFER_BODY_STAGE"),
    (lambda d: d.update(expected_body_sha256="f" * 64), "TRANSFER_BODY_HASH_MISMATCH"),
    (lambda d: d.update(requested_identifier="PMC12345"), "TRANSFER_IDENTIFIER"),
    (lambda d: d.update(declared_license_id="unknown"), "TRANSFER_DECLARED_LICENSE"),
    (lambda d: d.update(rights_evidence_uri="https://user:secret@example.org/license"), "PROVENANCE_URI_INVALID"),
    (lambda d: d.update(rights_evidence_uri="https://example.org/licence?token=secret"), "PROVENANCE_URI_INVALID"),
    (lambda d: d.update(captured_at_utc="2026-10-26T23:57:00+02:00"), "CAPTURE_TIMESTAMP_NOT_UTC"),
    (lambda d: d.update(provider_response_id="\nINJECT"), "PROVIDER_RESPONSE_ID"),
    (lambda d: d.update(schema_version="v2"), "TRANSFER_VERSION"),
])
def test_transfer_declaration_fail_closed(change, expected):
    raw = example()
    record = transfer(raw)
    change(record)
    with pytest.raises(vb.BenchmarkError, match=expected):
        pmc.derive(raw, record)


def test_malformed_declarations_and_size_limits_refused():
    raw = example()
    for data, reason in (
        (raw.replace(b"<GetRecord>", b'<!DOCTYPE article SYSTEM "file:///etc/passwd"><GetRecord>'),
         "ENVELOPE_DTD_OR_ENTITY"),
        (raw.replace(b"</record>", b"</other>"), "ENVELOPE_MALFORMED_XML"),
        (raw + b" \x00", "ENVELOPE_NOT_UTF8"),
        (b"a" * (pmc.MAX_ENVELOPE_BYTES + 1), "ENVELOPE_BYTE_LIMIT"),
    ):
        with pytest.raises(vb.BenchmarkError, match=reason):
            pmc.derive(data, transfer(data))


def test_cli_extraction_is_private_exclusive_and_replays(tmp_path: Path):
    raw = example()
    (tmp_path / "raw.xml").write_bytes(raw)
    (tmp_path / "transfer.json").write_bytes(vb.canonical_bytes(transfer(raw)))
    output = tmp_path / "derived.xml"
    cmd = [sys.executable, "-m", "tools.pmc_oai_envelope", "--action", "extract",
           "--raw-envelope", str(tmp_path / "raw.xml"), "--transfer",
           str(tmp_path / "transfer.json"), "--output-source", str(output)]
    run = subprocess.run(cmd, cwd=ROOT, capture_output=True, check=False)
    assert run.returncode == 0, run.stderr.decode()
    envelope = json.loads(run.stdout)
    assert envelope["receipt"]["derived_jats_sha256"] == sha256(output.read_bytes()).hexdigest()
    assert "Invented example" not in run.stdout.decode()
    if os.name != "nt":
        assert output.stat().st_mode & 0o077 == 0
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode == 2
    (tmp_path / "receipt.json").write_bytes(vb.canonical_bytes(envelope))
    check = subprocess.run([sys.executable, "-m", "tools.pmc_oai_envelope",
                            "--action", "replay", "--raw-envelope", str(tmp_path / "raw.xml"),
                            "--transfer", str(tmp_path / "transfer.json"),
                            "--derived-source", str(output),
                            "--receipt-envelope", str(tmp_path / "receipt.json"),
                            "--expected-receipt-sha256", envelope["receipt_sha256"]],
                           cwd=ROOT, capture_output=True)
    assert check.returncode == 0, check.stderr.decode()
    assert json.loads(check.stdout)["status"] == "RAW_SPAN_AND_DERIVED_JATS_REPLAYED"
