"""Bounded offline source capture and lineage tests (synthetic; no source claims)."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import source_capture_manifest as capture
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/synthetic-jats/denominator-trace.xml"


def xml() -> bytes:
    return EXAMPLE.read_bytes()


def metadata(data: bytes | None = None, *, record_id="article-v1",
             family_id="family-a", version="v1", kind="article",
             parent=None, time="2026-10-20T09:00:00Z",
             rights="declared_open_license") -> dict:
    raw = xml() if data is None else data
    return {
        "schema_version": capture.METADATA_VERSION,
        "record_id": record_id,
        "work_family_id": family_id,
        "version_id": version,
        "kind": kind,
        "parent_record_id": parent,
        "correction_notice_uri": (
            "https://example.org/corrections/notice-1" if kind == "correction" else None
        ),
        "origin": {
            "retrieval_route": "publisher_open_access",
            "capture_uri": "https://example.org/articles/original.xml",
            "publisher_uri": "https://example.org/articles/original",
            "captured_at_utc": time,
            "expected_source_sha256": sha256(raw).hexdigest(),
        },
        "rights": {
            "classification": rights,
            "license_id": "CC-BY-4.0" if rights == "declared_open_license" else None,
            "evidence_uri": "https://example.org/license" if rights in (
                "declared_open_license", "documented_permission") else None,
        },
        "exposure": {
            "partition": "development_exposed",
            "prior_access": "known_exposed",
            "label_status": "no_independent_scientific_label",
        },
    }


def item(data: bytes, meta: dict) -> dict:
    return capture.envelope(capture.build_capture(data, meta))


def test_declared_capture_replays_byte_exactly_and_no_raw_paper_text_in_metadata():
    raw = xml()
    meta = metadata(raw)
    declared = capture.build_capture(raw, meta)
    env = capture.envelope(declared)
    assert declared["schema_version"] == capture.MANIFEST_VERSION
    assert declared["source_sha256"] == sha256(raw).hexdigest()
    assert declared["source_bytes"] == len(raw)
    assert declared["source_xml_root"] == "article"
    assert all(declared[key] is False for key in (
        "publication_authenticity_verified",
        "rights_verified_by_tool",
        "captured_at_authenticity_verified",
        "scientific_label_established",
        "protected_evaluation_permitted",
    ))
    assert "Direct printed ratio" not in json.dumps(env)
    assert capture.replay_capture(raw, meta, env,
                                  expected_manifest_sha256=env["manifest_sha256"])[
        "status"] == "SOURCE_BYTES_AND_DECLARED_METADATA_REPLAYED"


def test_capture_is_deterministic_not_timestamped_by_python():
    raw, meta = xml(), metadata()
    a = item(raw, meta)
    b = item(raw, deepcopy(meta))
    assert vb.canonical_bytes(a) == vb.canonical_bytes(b)
    assert a["manifest_sha256"] == b["manifest_sha256"]


def test_raw_change_and_metadata_change_fail_exact_capture_replay():
    raw, meta = xml(), metadata()
    env = item(raw, meta)
    amended = raw.replace(b"Matching count", b"Amended label", 1)
    with pytest.raises(vb.BenchmarkError, match="SOURCE_HASH_MISMATCH"):
        capture.replay_capture(amended, meta, env,
                               expected_manifest_sha256=env["manifest_sha256"])
    other = deepcopy(meta)
    other["origin"]["captured_at_utc"] = "2026-10-20T10:00:00Z"
    with pytest.raises(vb.BenchmarkError, match="SOURCE_CAPTURE_REPLAY_MISMATCH"):
        capture.replay_capture(raw, other, env,
                               expected_manifest_sha256=env["manifest_sha256"])
    with pytest.raises(vb.BenchmarkError, match="EXTERNAL_MANIFEST_PIN_MISMATCH"):
        capture.replay_capture(raw, meta, env,
                               expected_manifest_sha256="f" * 64)


@pytest.mark.parametrize(("field", "value", "diagnostic"), [
    ("kind", "retired", "SOURCE_KIND"),
    ("version_id", "bad identifier!", "SOURCE_IDENTIFIER"),
    ("parent_record_id", "source-v0", "SOURCE_INITIAL_HAS_PARENT"),
    ("correction_notice_uri", "https://example.org/correction", "UNEXPECTED_CORRECTION_NOTICE"),
])
def test_malformed_identity_and_correction_status_refused(field, value, diagnostic):
    meta = metadata()
    meta[field] = value
    with pytest.raises(vb.BenchmarkError, match=diagnostic):
        capture.build_capture(xml(), meta)


def test_correction_requires_parent_and_notice():
    meta = metadata(kind="correction", version="v2", record_id="corr-v2",
                    parent="article-v1", time="2026-10-21T12:00:00Z")
    capture.build_capture(xml(), meta)
    meta["correction_notice_uri"] = None
    with pytest.raises(vb.BenchmarkError, match="CORRECTION_NOTICE_REQUIRED"):
        capture.build_capture(xml(), meta)


@pytest.mark.parametrize(("key", "value", "diagnostic"), [
    ("capture_uri", "https://user:token@example.org/paper.xml", "PROVENANCE_URI_INVALID"),
    ("publisher_uri", "http://example.org/article", "PROVENANCE_URI_INVALID"),
    ("capture_uri", "https://example.org/get?token=private", "PROVENANCE_URI_INVALID"),
    ("captured_at_utc", "2026-02-30T10:00:00Z", "CAPTURE_TIMESTAMP_INVALID"),
    ("captured_at_utc", "2026-10-20T10:00:00+02:00", "CAPTURE_TIMESTAMP_NOT_UTC"),
])
def test_untrusted_retrieval_strings_rejected_without_external_calls(key, value, diagnostic):
    meta = metadata()
    meta["origin"][key] = value
    with pytest.raises(vb.BenchmarkError, match=diagnostic):
        capture.build_capture(xml(), meta)


def test_supplied_local_source_has_explicit_absent_retrieval_uri():
    meta = metadata(rights="unknown")
    meta["origin"]["retrieval_route"] = "operator_supplied"
    meta["origin"]["capture_uri"] = None
    out = capture.build_capture(xml(), meta)
    assert out["rights_verified_by_tool"] is False
    assert out["metadata"]["rights"]["classification"] == "unknown"
    meta["origin"]["retrieval_route"] = "publisher_open_access"
    with pytest.raises(vb.BenchmarkError, match="RETRIEVAL_URI_REQUIRED"):
        capture.build_capture(xml(), meta)


def test_rights_unknown_or_restricted_cannot_pretend_legal_clearance():
    for value in ("unknown", "restricted", "documented_permission"):
        meta = metadata(rights=value)
        manifest = capture.build_capture(xml(), meta)
        assert manifest["rights_verified_by_tool"] is False
        assert manifest["protected_evaluation_permitted"] is False
    meta = metadata(rights="declared_open_license")
    meta["rights"]["evidence_uri"] = None
    with pytest.raises(vb.BenchmarkError, match="DECLARED_OPEN_LICENSE_EVIDENCE_REQUIRED"):
        capture.build_capture(xml(), meta)
    meta = metadata(rights="unknown")
    meta["rights"]["license_id"] = "CC-BY-4.0"
    with pytest.raises(vb.BenchmarkError, match="UNVERIFIED_RIGHTS_CANNOT_CLAIM_LICENSE"):
        capture.build_capture(xml(), meta)


def test_sealed_labels_and_protected_partition_never_accepted():
    meta = metadata()
    meta["exposure"]["partition"] = "sealed_confirmatory"
    with pytest.raises(vb.BenchmarkError, match="PROTECTED_PARTITION_FORBIDDEN"):
        capture.build_capture(xml(), meta)
    meta["exposure"]["partition"] = "development_exposed"
    meta["exposure"]["label_status"] = "scientific_gold"
    with pytest.raises(vb.BenchmarkError, match="UNSUPPORTED_SCIENTIFIC_LABEL"):
        capture.build_capture(xml(), meta)


def test_source_xml_is_not_just_arbitrary_file_with_sha256():
    bad = b"<non-jats><p>not a paper</p></non-jats>"
    with pytest.raises(ValueError, match="article root"):
        capture.build_capture(bad, metadata(bad))
    evil = (b'<!DOCTYPE a [ <!ENTITY secret SYSTEM "file:///etc/passwd"> ]>'
            b"<article><body>&secret;</body></article>")
    with pytest.raises(ValueError):
        capture.build_capture(evil, metadata(evil))


def captures():
    first = xml()
    second = first.replace(b"Matching count", b"Correction sample", 1)
    supplement = first.replace(b"Matching count", b"Supplement sample", 1)
    another = first.replace(b"Matching count", b"Different family case", 1)
    a = item(first, metadata(first))
    c = item(second, metadata(second, record_id="correction-v2", version="v2",
                              kind="correction", parent="article-v1",
                              time="2026-10-21T10:00:00Z"))
    s = item(supplement, metadata(supplement, record_id="supplement-v3", version="v3",
                                  kind="supplement", parent="article-v1",
                                  time="2026-10-22T10:00:00Z"))
    b = item(another, metadata(another, record_id="other-article",
                               family_id="family-b", version="v1",
                               time="2026-10-23T10:00:00Z"))
    reg = {"schema_version": capture.REGISTRY_INPUT_VERSION,
           "captures": [a, c, s, b]}
    return reg


def checked_registry(reg):
    return capture.validate_registry(reg, expected_registry_sha256=vb.commitment(reg))


def test_version_correction_supplement_group_by_declared_family():
    reg = captures()
    report = checked_registry(reg)
    assert report["record_count"] == 4
    assert report["declared_work_family_count"] == 2
    assert report["distinct_source_byte_hash_count"] == 4
    assert report["families"] == [
        {"work_family_id": "family-a",
         "record_ids": ["article-v1", "correction-v2", "supplement-v3"],
         "version_count": 3},
        {"work_family_id": "family-b",
         "record_ids": ["other-article"], "version_count": 1},
    ]
    assert report["source_bytes_replayed_by_registry"] is False
    assert report["scientific_family_independence_established"] is False
    assert report["protected_holdout_qualified"] is False


def test_duplicate_record_or_version_id_not_silently_counted_twice():
    reg = captures()
    reg["captures"].append(deepcopy(reg["captures"][0]))
    with pytest.raises(vb.BenchmarkError, match="DUPLICATE_SOURCE_RECORD"):
        checked_registry(reg)
    reg = captures()
    reg["captures"][1]["manifest"]["metadata"]["version_id"] = "v1"
    reg["captures"][1]["manifest_sha256"] = vb.commitment(reg["captures"][1]["manifest"])
    with pytest.raises(vb.BenchmarkError, match="DUPLICATE_WORK_FAMILY_VERSION"):
        checked_registry(reg)


def test_identical_bytes_cannot_fake_a_new_version_in_same_family():
    reg = captures()
    correction = reg["captures"][1]
    correction["manifest"]["source_sha256"] = reg["captures"][0]["manifest"]["source_sha256"]
    correction["manifest"]["source_bytes"] = reg["captures"][0]["manifest"]["source_bytes"]
    correction["manifest"]["metadata"]["origin"]["expected_source_sha256"] = (
        reg["captures"][0]["manifest"]["source_sha256"]
    )
    correction["manifest_sha256"] = vb.commitment(correction["manifest"])
    with pytest.raises(vb.BenchmarkError, match="SOURCE_BYTES_REUSED_AS_NEW_VERSION"):
        checked_registry(reg)


def test_malformed_envelope_rejected_without_keyerror_traceback():
    raw, meta = xml(), metadata()
    with pytest.raises(vb.BenchmarkError, match="CAPTURE_ENVELOPE_FIELDS"):
        capture.replay_capture(
            raw, meta, {"missing_manifest": True},
            expected_manifest_sha256="0" * 64,
        )


def test_same_identical_source_bytes_cannot_claim_another_independent_family():
    reg = captures()
    reg["captures"][3] = deepcopy(reg["captures"][0])
    rec = reg["captures"][3]
    rec["manifest"]["metadata"]["record_id"] = "different-record"
    rec["manifest"]["metadata"]["work_family_id"] = "family-b"
    rec["manifest_sha256"] = vb.commitment(rec["manifest"])
    with pytest.raises(vb.BenchmarkError, match="SAME_SOURCE_BYTES_IN_DIFFERENT_FAMILIES"):
        checked_registry(reg)


def test_missing_or_cross_family_parent_and_chronology_are_rejected():
    reg = captures()
    reg["captures"][1]["manifest"]["metadata"]["parent_record_id"] = "does-not-exist"
    reg["captures"][1]["manifest_sha256"] = vb.commitment(reg["captures"][1]["manifest"])
    with pytest.raises(vb.BenchmarkError, match="LINEAGE_PARENT_MISSING"):
        checked_registry(reg)
    reg = captures()
    reg["captures"][1]["manifest"]["metadata"]["parent_record_id"] = "other-article"
    reg["captures"][1]["manifest_sha256"] = vb.commitment(reg["captures"][1]["manifest"])
    with pytest.raises(vb.BenchmarkError, match="LINEAGE_PARENT_DIFFERENT_FAMILY"):
        checked_registry(reg)
    reg = captures()
    reg["captures"][1]["manifest"]["metadata"]["origin"]["captured_at_utc"] = (
        "2026-10-01T08:00:00Z")
    reg["captures"][1]["manifest_sha256"] = vb.commitment(reg["captures"][1]["manifest"])
    with pytest.raises(vb.BenchmarkError, match="LINEAGE_TIMESTAMP_ORDER"):
        checked_registry(reg)


def test_lineage_cycle_does_not_pass_even_if_capture_clock_is_equal():
    reg = captures()
    # Convert the root to a revision in a deliberate mutual-parent loop.
    root = reg["captures"][0]
    root["manifest"]["metadata"]["kind"] = "revision"
    root["manifest"]["metadata"]["parent_record_id"] = "correction-v2"
    root["manifest"]["metadata"]["origin"]["captured_at_utc"] = "2026-10-21T10:00:00Z"
    root["manifest_sha256"] = vb.commitment(root["manifest"])
    with pytest.raises(vb.BenchmarkError, match="LINEAGE_CYCLE"):
        checked_registry(reg)


def test_registry_uses_external_pin_not_self_reported_hash_as_trust():
    reg = captures()
    before = vb.commitment(reg)
    reg["captures"][0]["manifest"]["metadata"]["rights"]["classification"] = "unknown"
    reg["captures"][0]["manifest"]["metadata"]["rights"]["license_id"] = None
    reg["captures"][0]["manifest"]["metadata"]["rights"]["evidence_uri"] = None
    reg["captures"][0]["manifest_sha256"] = vb.commitment(reg["captures"][0]["manifest"])
    with pytest.raises(vb.BenchmarkError, match="REGISTRY_INPUT_PIN_MISMATCH"):
        capture.validate_registry(reg, expected_registry_sha256=before)


def test_forged_manifest_self_verified_but_not_original_source_replayed():
    data, meta = xml(), metadata()
    env = item(data, meta)
    env["manifest"]["source_bytes"] += 1
    env["manifest_sha256"] = vb.commitment(env["manifest"])
    with pytest.raises(vb.BenchmarkError, match="SOURCE_CAPTURE_REPLAY_MISMATCH"):
        capture.replay_capture(data, meta, env,
                               expected_manifest_sha256=env["manifest_sha256"])


def test_illegal_authority_flags_rejected_in_registry_without_paper_bytes():
    reg = captures()
    reg["captures"][0]["manifest"]["protected_evaluation_permitted"] = True
    reg["captures"][0]["manifest_sha256"] = vb.commitment(reg["captures"][0]["manifest"])
    with pytest.raises(vb.BenchmarkError, match="FALSE_AUTHORITY_CLAIM"):
        checked_registry(reg)


def test_cli_capture_replay_and_registry_roundtrip(tmp_path):
    raw, meta = xml(), metadata()
    src = tmp_path / "source.xml"
    info = tmp_path / "metadata.json"
    src.write_bytes(raw)
    info.write_bytes(vb.canonical_bytes(meta))
    def run(*args):
        return subprocess.run([sys.executable, "-m", "tools.source_capture_manifest",
                               *map(str, args)], cwd=ROOT, capture_output=True,
                              timeout=40)
    prepared = run("--action", "capture", "--source", src, "--metadata", info)
    assert prepared.returncode == 0, prepared.stderr
    assert b"\r\n" not in prepared.stdout
    env = json.loads(prepared.stdout)
    assert env == item(raw, meta)
    envfile = tmp_path / "capture.json"
    envfile.write_bytes(vb.canonical_bytes(env))
    replayed = run("--action", "replay", "--source", src, "--metadata", info,
                   "--capture-envelope", envfile, "--expected-manifest-sha256",
                   env["manifest_sha256"])
    assert replayed.returncode == 0, replayed.stderr
    assert json.loads(replayed.stdout)["eligible_for_protected_evaluation"] is False
    registry = {"schema_version": capture.REGISTRY_INPUT_VERSION, "captures": [env]}
    regfile = tmp_path / "registry.json"
    regfile.write_bytes(vb.canonical_bytes(registry))
    result = run("--action", "registry", "--registry", regfile,
                 "--expected-registry-sha256", vb.commitment(registry))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["declared_work_family_count"] == 1
    assert b"\r\n" not in result.stdout
    bad = run("--action", "replay", "--source", src, "--metadata", info,
              "--capture-envelope", envfile, "--expected-manifest-sha256", "f" * 64)
    assert bad.returncode == 2
    assert json.loads(bad.stderr)["code"] == "EXTERNAL_MANIFEST_PIN_MISMATCH"


def test_duplicate_json_keys_and_untrusted_raw_source_are_not_echoed(tmp_path):
    raw, meta = xml(), metadata()
    src = tmp_path / "paper.xml"
    info = tmp_path / "meta.json"
    src.write_bytes(raw)
    info.write_bytes(vb.canonical_bytes(meta).replace(
        b'"record_id":', b'"record_id": "malicious", "record_id":', 1))
    r = subprocess.run([
        sys.executable, "-m", "tools.source_capture_manifest",
        "--action", "capture", "--source", str(src), "--metadata", str(info),
    ], cwd=ROOT, capture_output=True, timeout=40)
    assert r.returncode == 2
    assert json.loads(r.stderr)["code"] == "DUPLICATE_JSON_KEY"
    assert b"Direct printed ratio" not in r.stderr


def test_symlinked_source_is_denied(tmp_path):
    symlink = tmp_path / "alias.xml"
    try:
        symlink.symlink_to(EXAMPLE)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unsupported")
    meta = tmp_path / "meta.json"
    meta.write_bytes(vb.canonical_bytes(metadata()))
    r = subprocess.run([
        sys.executable, "-m", "tools.source_capture_manifest",
        "--action", "capture", "--source", str(symlink), "--metadata", str(meta),
    ], cwd=ROOT, capture_output=True, timeout=40)
    assert r.returncode == 2
    assert json.loads(r.stderr)["status"] == "invalid"
