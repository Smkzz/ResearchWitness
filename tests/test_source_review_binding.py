"""Synthetic contracts for linking RW-01K captures to RW-01J review packets."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import denominator_scope_review as scope
from tools import source_capture_manifest as capture
from tools import source_review_binding as binding
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/synthetic-jats/denominator-trace.xml"


def records():
    data = FIXTURE.read_bytes()
    meta = {
        "schema_version": capture.METADATA_VERSION,
        "record_id": "invented-article-v1",
        "work_family_id": "invented-family",
        "version_id": "v1",
        "kind": "article",
        "parent_record_id": None,
        "correction_notice_uri": None,
        "origin": {
            "retrieval_route": "operator_supplied",
            "capture_uri": None,
            "publisher_uri": None,
            "captured_at_utc": "2026-10-26T18:00:00Z",
            "expected_source_sha256": sha256(data).hexdigest(),
        },
        "rights": {"classification": "unknown", "license_id": None, "evidence_uri": None},
        "exposure": {
            "partition": "development_exposed",
            "prior_access": "known_exposed",
            "label_status": "no_independent_scientific_label",
        },
    }
    captured = capture.envelope(capture.build_capture(data, meta))
    packet = scope.make_packet(data)
    packet_envelope = {"packet": packet, "packet_sha256": vb.commitment(packet)}
    return data, meta, captured, packet_envelope


def evaluate(data, metadata, capture_env, packet_env, **kwargs):
    return binding.bind(
        data, metadata, capture_env, packet_env,
        expected_capture_sha256=capture_env["manifest_sha256"],
        expected_packet_sha256=packet_env["packet_sha256"], **kwargs,
    )


def test_exact_same_bytes_are_bound_without_claiming_truth():
    data, meta, cap, packet = records()
    r = evaluate(data, meta, cap, packet)
    assert r["record_id"] == meta["record_id"]
    assert r["work_family_id_declared"] == meta["work_family_id"]
    assert r["source_sha256"] == sha256(data).hexdigest()
    assert r["relation_count"] == 3
    assert r["review_status"] == "REVIEWS_NOT_SUPPLIED"
    assert r["scientific_scope_truth_established"] is False
    assert r["rights_verified_by_tool"] is False
    assert r["family_independence_authenticated"] is False
    assert r["protected_evaluation_permitted"] is False
    assert r == evaluate(data, meta, cap, packet)


def test_source_version_tampering_rejected_without_guessing():
    data, meta, cap, packet = records()
    edited = data.replace(b"N=50", b"N=20", 1)
    with pytest.raises(vb.BenchmarkError, match="SOURCE_HASH_MISMATCH"):
        evaluate(edited, meta, cap, packet)


def test_mismatched_source_capture_declaration_rejected():
    data, meta, cap, packet = records()
    other = deepcopy(meta)
    other["version_id"] = "v2"
    with pytest.raises(vb.BenchmarkError, match="SOURCE_CAPTURE_REPLAY_MISMATCH"):
        evaluate(data, other, cap, packet)


def test_capture_commitment_pin_is_checked():
    data, meta, cap, packet = records()
    with pytest.raises(vb.BenchmarkError, match="EXTERNAL_MANIFEST_PIN_MISMATCH"):
        binding.bind(data, meta, cap, packet,
                     expected_capture_sha256="f" * 64,
                     expected_packet_sha256=packet["packet_sha256"])


def test_packet_digest_and_source_facts_checked():
    data, meta, cap, packet = records()
    forged = deepcopy(packet)
    forged["packet"]["relations"][0]["facts"][0]["printed_integer"] = 123456
    forged["packet_sha256"] = vb.commitment(forged["packet"])
    with pytest.raises(vb.BenchmarkError, match="PACKET_SOURCE_REPLAY_MISMATCH"):
        evaluate(data, meta, cap, forged)


def test_cannot_supply_only_one_reviewer_record():
    data, meta, cap, packet = records()
    with pytest.raises(vb.BenchmarkError, match="BOTH_REVIEWS_REQUIRED_OR_OMITTED"):
        evaluate(data, meta, cap, packet, review_a={})


def test_unsupported_protected_partition_cannot_be_declared():
    data, meta, cap, packet = records()
    bad = deepcopy(meta)
    bad["exposure"]["partition"] = "sealed_confirmatory"
    with pytest.raises(vb.BenchmarkError, match="PROTECTED_PARTITION_FORBIDDEN"):
        evaluate(data, bad, cap, packet)


def test_cli_checks_legal_envelope_types_and_lf_stdout(tmp_path):
    data, meta, cap, packet = records()
    paths = {}
    for key, content in (
        ("source", data),
        ("metadata", vb.canonical_bytes(meta)),
        ("capture", vb.canonical_bytes(cap)),
        ("packet", vb.canonical_bytes(packet)),
    ):
        path = tmp_path / (key + (".xml" if key == "source" else ".json"))
        path.write_bytes(content)
        paths[key] = str(path)
    command = [
        sys.executable, "-m", "tools.source_review_binding",
        "--source", paths["source"], "--metadata", paths["metadata"],
        "--capture-envelope", paths["capture"],
        "--expected-capture-sha256", cap["manifest_sha256"],
        "--packet-envelope", paths["packet"],
        "--expected-packet-sha256", packet["packet_sha256"],
    ]
    r = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=40)
    assert r.returncode == 0, r.stderr
    assert b"\r\n" not in r.stdout
    assert json.loads(r.stdout)["review_status"] == "REVIEWS_NOT_SUPPLIED"
    changed = list(command)
    changed[-1] = "0" * 64
    invalid = subprocess.run(changed, cwd=ROOT, capture_output=True, timeout=40)
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)["code"] == "PACKET_ENVELOPE_PIN"


def test_duplicate_json_keys_fail_without_private_data_echo(tmp_path):
    data, meta, cap, packet = records()
    p = tmp_path / "metadata.json"
    original = vb.canonical_bytes(meta)
    p.write_bytes(original.replace(b'"record_id":', b'"record_id":"extra","record_id":', 1))
    with pytest.raises(vb.BenchmarkError, match="DUPLICATE_JSON_KEY"):
        vb.parse_document(p.read_bytes())


def test_source_symlink_rejected(tmp_path):
    link = tmp_path / "link.xml"
    try:
        link.symlink_to(FIXTURE)
    except (OSError, NotImplementedError):
        pytest.skip("No symlink support on this runner")
    from tools.offline_files import read_regular
    with pytest.raises(ValueError):
        read_regular(link, 8 * 1024 * 1024)
