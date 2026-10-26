"""RW-01J development-source review protocol; synthetic labels are NOT scientific gold."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import denominator_scope_review as scope
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/synthetic-jats/denominator-trace.xml"


def fixtures(source: bytes | None = None):
    data = SOURCE.read_bytes() if source is None else source
    packet = scope.make_packet(data)
    digest = vb.commitment(packet)
    def review(name: str, method: str = "synthetic_demonstration"):
        rows = []
        for rel in packet["relations"]:
            facts = rel["facts"]
            if facts:
                chosen = facts[0]["fact_id"]
                row = {
                    "relation_id": rel["relation_id"],
                    "decision": "same_scope_proposed",
                    "selected_fact_id": chosen,
                    "basis_fact_ids": [chosen],
                    "scope_dimensions": {name: "explicitly_same" for name in scope.DIMENSIONS},
                    "rationale": (
                        "Invented developer-only scope declaration by " + name +
                        " linked to source evidence, NOT a verified real study."
                    ),
                }
            else:
                row = {
                    "relation_id": rel["relation_id"],
                    "decision": "unresolved",
                    "selected_fact_id": None,
                    "basis_fact_ids": [],
                    "scope_dimensions": {name: "unstated" for name in scope.DIMENSIONS},
                    "rationale": (
                        "Unresolved developer-only relation by " + name +
                        ": no source fact was captured for this percentage."
                    ),
                }
            rows.append(row)
        return {
            "schema_version": scope.REVIEW_VERSION,
            "packet_sha256": digest,
            "reviewer_id": name,
            "review_method": method,
            "independence_declared": False,
            "rows": rows,
        }
    return data, packet, review("fictional-a"), review("fictional-b"), digest


def reconcile(data, packet, a, b, digest):
    return scope.reconcile(data, packet, a, b,
                           expected_source_sha256=sha256(data).hexdigest(),
                           expected_packet_sha256=digest)


def test_blinded_source_packet_carries_raw_element_evidence_without_detector_decisions():
    data, packet, a, b, digest = fixtures()
    assert packet["schema_version"] == scope.PACKET_VERSION
    assert packet["source_sha256"] == sha256(data).hexdigest()
    assert packet["packet_generation"] == "existing_detector_source_fact_projection"
    assert packet["detector_verdict_and_selected_base_included"] is False
    text = json.dumps(packet)
    for phrase in ("detector_status", "detector_denominator",
                   "detector_reason", "arithmetic_mismatch_candidate",
                   "numeric_equals_detector_base"):
        assert phrase not in text
    assert len(packet["relations"]) == 3
    for rel in packet["relations"]:
        for entry in [rel["relation_source_anchor"]] + [
            f["source_anchor"] for f in rel["facts"]
        ]:
            assert entry["source_sha256"] == sha256(data).hexdigest()
            assert entry["start_byte"] < entry["end_byte"]
            assert data[entry["start_byte"]:entry["end_byte"]].startswith(
                (b"<td", b"<th", b"<p", b"<caption", b"<label")
            )
            assert entry["range_semantics"].startswith("original_xml_element")
    assert scope.packet_commitment(packet) == digest


def test_concordant_development_demonstration_does_not_promote_scientific_truth():
    data, packet, a, b, digest = fixtures()
    output = reconcile(data, packet, a, b, digest)
    assert output["schema_version"] == scope.RESULT_VERSION
    assert output["registered_relation_count"] == 3
    assert output["status_counts"] == {
        "BOTH_DECLARED_UNRESOLVED": 1,
        "DECLARED_CONCORDANCE_NOT_AUTHENTICATED": 2,
    }
    assert output["reviewer_independence_authenticated"] is False
    assert output["scientific_truth_established"] is False
    assert output["protected_custody_qualified"] is False
    assert all(not row["scientific_label_independently_authenticated"]
               and not row["ready_for_sealed_evaluation"] for row in output["relations"])


def test_opposed_reviewer_assessment_preserved_as_disagreement():
    data, packet, a, b, digest = fixtures()
    b["rows"][0]["decision"] = "different_scope_proposed"
    b["rows"][0]["scope_dimensions"]["analysis_set"] = "explicitly_different"
    output = reconcile(data, packet, a, b, digest)
    assert output["relations"][0]["state"] == "REVIEWER_DISAGREEMENT_OR_INCOMPLETE"
    assert output["status_counts"]["REVIEWER_DISAGREEMENT_OR_INCOMPLETE"] == 1


def test_header_caption_conflict_overrides_matching_opinions():
    data = SOURCE.read_bytes().replace(b"Patients, n (%) N=50", b"Patients, n (%) N=20")
    data, packet, a, b, digest = fixtures(data)
    result = reconcile(data, packet, a, b, digest)
    assert len({f["printed_integer"] for f in packet["relations"][0]["facts"]}) == 2
    assert result["relations"][0]["state"] == "VISIBLE_BASE_CONFLICT_REQUIRES_ADJUDICATION"
    assert result["scientific_truth_established"] is False


def test_identically_copied_rows_remain_independence_blocked():
    data, packet, a, b, digest = fixtures()
    # Different display names do not make word-for-word identical records
    # independent scientific reviews.
    b["rows"] = deepcopy(a["rows"])
    result = reconcile(data, packet, a, b, digest)
    assert result["status_counts"]["IDENTICAL_REVIEW_RECORDS_REQUIRE_INDEPENDENCE_CHECK"] == 3
    assert result["reviewer_independence_authenticated"] is False


def test_outcome_preference_fields_do_not_affect_source_packet(monkeypatch):
    data, packet, _a, _b, _digest = fixtures()
    from researchwitness import jats_denominator_trace
    original = jats_denominator_trace.trace_denominators(data)
    modified = deepcopy(original)
    for row in modified["relations"]:
        row["detector_status"] = "rounding_ambiguous"
        row["detector_denominator"] = 999
        row["detector_denominator_scope"] = "invented"
        for fact in row["denominator_facts"]:
            fact["numeric_equals_detector_base"] = not fact["numeric_equals_detector_base"]
        row["denominator_facts"].reverse()
    monkeypatch.setattr(scope, "trace_denominators", lambda _source: modified)
    assert scope.make_packet(data) == packet
    assert vb.commitment(scope.make_packet(data)) == vb.commitment(packet)


def test_non_hashable_source_reference_is_rejected_cleanly():
    data, packet, a, b, digest = fixtures()
    a["rows"][0]["basis_fact_ids"] = [{"malicious": "object"}]
    with pytest.raises(vb.BenchmarkError, match="REVIEW_BASIS_REFERENCE_LIST"):
        reconcile(data, packet, a, b, digest)


def test_a_reviewer_id_is_not_evidence_of_independent_identity():
    data, packet, a, b, digest = fixtures()
    b["reviewer_id"] = a["reviewer_id"]
    with pytest.raises(vb.BenchmarkError, match="REVIEWER_ID_REUSED"):
        reconcile(data, packet, a, b, digest)
    b["reviewer_id"] = "different-name"
    a["independence_declared"] = b["independence_declared"] = True
    out = reconcile(data, packet, a, b, digest)
    assert out["reviewer_independence_authenticated"] is False


def test_all_registered_relations_must_have_exactly_one_review_in_order():
    data, packet, a, b, digest = fixtures()
    b["rows"].pop()
    with pytest.raises(vb.BenchmarkError, match="REVIEW_COVERAGE"):
        reconcile(data, packet, a, b, digest)
    b["rows"] = [deepcopy(a["rows"][0])] + deepcopy(a["rows"][1:])
    b["rows"][1] = deepcopy(a["rows"][0])
    with pytest.raises(vb.BenchmarkError, match="REVIEW_RELATION_ORDER_OR_ID"):
        reconcile(data, packet, a, b, digest)


@pytest.mark.parametrize(("bad_fact", "bad_references", "diagnostic"), [
    ("invented-fact", None, "REVIEW_SELECTED_FACT_INVALID"),
    (None, ["invented-fact"], "REVIEW_SOURCE_REFERENCE_MISSING"),
    (None, [], "REVIEW_SAME_SCOPE_NOT_ESTABLISHED_BY_DECLARATION"),
])
def test_fabricated_or_unreferenced_denominator_fact_refused(
        bad_fact, bad_references, diagnostic):
    data, packet, a, b, digest = fixtures()
    if bad_fact is not None:
        a["rows"][0]["selected_fact_id"] = bad_fact
    if bad_references is not None:
        a["rows"][0]["basis_fact_ids"] = bad_references
    with pytest.raises(vb.BenchmarkError, match=diagnostic):
        reconcile(data, packet, a, b, digest)


def test_duplicate_reference_and_invalid_scope_refused():
    data, packet, a, b, digest = fixtures()
    fact = a["rows"][0]["selected_fact_id"]
    a["rows"][0]["basis_fact_ids"] = [fact, fact]
    with pytest.raises(vb.BenchmarkError, match="REVIEW_BASIS_REFERENCE_LIST"):
        reconcile(data, packet, a, b, digest)
    a["rows"][0]["basis_fact_ids"] = [fact]
    a["rows"][0]["scope_dimensions"]["timepoint"] = "unstated"
    with pytest.raises(vb.BenchmarkError, match="REVIEW_SAME_SCOPE_NOT_ESTABLISHED"):
        reconcile(data, packet, a, b, digest)


def test_one_source_has_no_candidate_fact_so_it_cannot_be_certified():
    data, packet, a, b, digest = fixtures()
    assert packet["relations"][2]["facts"] == []
    a["rows"][2]["decision"] = "same_scope_proposed"
    a["rows"][2]["selected_fact_id"] = "fabricated"
    with pytest.raises(vb.BenchmarkError, match="REVIEW_SELECTED_FACT_INVALID"):
        reconcile(data, packet, a, b, digest)


def test_external_source_and_packet_pins_and_full_replay_refuse_fabrication():
    data, packet, a, b, digest = fixtures()
    with pytest.raises(vb.BenchmarkError, match="SOURCE_PIN_MISMATCH"):
        scope.reconcile(data, packet, a, b,
                        expected_source_sha256="0" * 64,
                        expected_packet_sha256=digest)
    with pytest.raises(vb.BenchmarkError, match="PACKET_PIN_MISMATCH"):
        reconcile(data, packet, a, b, "f" * 64)
    edited = deepcopy(packet)
    edited["relations"][0]["facts"][0]["printed_integer"] = 999
    new_pin = vb.commitment(edited)
    for review in (a, b):
        review["packet_sha256"] = new_pin
    with pytest.raises(vb.BenchmarkError, match="PACKET_SOURCE_REPLAY_MISMATCH"):
        reconcile(data, edited, a, b, new_pin)
    amended = data.replace(b"N=50", b"N=20", 1)
    with pytest.raises(vb.BenchmarkError, match="SOURCE_PIN_MISMATCH"):
        scope.reconcile(amended, packet, a, b,
                        expected_source_sha256=sha256(data).hexdigest(),
                        expected_packet_sha256=digest)


def test_reviewer_mode_and_untrusted_extra_fields_rejected():
    data, packet, a, b, digest = fixtures()
    a["review_method"] = "sealed_protected"
    with pytest.raises(vb.BenchmarkError, match="REVIEW_METHOD_UNSUPPORTED"):
        reconcile(data, packet, a, b, digest)
    a["review_method"] = "synthetic_demonstration"
    a["paper_error_established"] = True
    with pytest.raises(vb.BenchmarkError, match="REVIEW_FIELDS"):
        reconcile(data, packet, a, b, digest)


def test_cli_prepare_and_reconcile_with_external_hashes(tmp_path):
    data, packet, a, b, digest = fixtures()
    source_file = tmp_path / "source.xml"
    source_file.write_bytes(data)
    prepare = subprocess.run([
        sys.executable, "-m", "tools.denominator_scope_review",
        "--action", "prepare", "--source", str(source_file),
        "--expected-source-sha256", sha256(data).hexdigest(),
    ], cwd=ROOT, capture_output=True, timeout=40)
    assert prepare.returncode == 0, prepare.stderr
    assert b"\r\n" not in prepare.stdout
    prepared = json.loads(prepare.stdout)
    assert prepared["packet"] == packet
    assert prepared["packet_sha256"] == digest
    packet_file = tmp_path / "packet.json"
    packet_file.write_bytes(vb.canonical_bytes(prepared))
    a_file, b_file = tmp_path / "review-a.json", tmp_path / "review-b.json"
    a_file.write_bytes(vb.canonical_bytes(a))
    b_file.write_bytes(vb.canonical_bytes(b))
    args = [
        sys.executable, "-m", "tools.denominator_scope_review",
        "--action", "reconcile", "--source", str(source_file),
        "--expected-source-sha256", sha256(data).hexdigest(),
        "--packet", str(packet_file),
        "--expected-packet-sha256", digest,
        "--review-a", str(a_file), "--review-b", str(b_file),
    ]
    result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stderr
    assert b"\r\n" not in result.stdout
    assert json.loads(result.stdout)["scientific_truth_established"] is False
    result2 = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=40)
    assert result2.stdout == result.stdout
    args[args.index(digest)] = "0" * 64
    failed = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=40)
    assert failed.returncode == 2
    assert json.loads(failed.stderr)["code"] == "PACKET_ENVELOPE_PIN"


def test_json_duplicate_keys_are_rejected_without_echoing_user_text(tmp_path):
    data, packet, a, b, digest = fixtures()
    source_file = tmp_path / "source.xml"
    source_file.write_bytes(data)
    (tmp_path / "packet.json").write_bytes(
        vb.canonical_bytes({"packet": packet, "packet_sha256": digest}))
    (tmp_path / "a.json").write_bytes(
        vb.canonical_bytes(a).replace(b'"reviewer_id":',
        b'"reviewer_id":"duplicate", "reviewer_id":', 1))
    (tmp_path / "b.json").write_bytes(vb.canonical_bytes(b))
    r = subprocess.run([
        sys.executable, "-m", "tools.denominator_scope_review",
        "--action", "reconcile", "--source", str(source_file),
        "--expected-source-sha256", sha256(data).hexdigest(),
        "--packet", str(tmp_path / "packet.json"),
        "--expected-packet-sha256", digest,
        "--review-a", str(tmp_path / "a.json"), "--review-b", str(tmp_path / "b.json"),
    ], cwd=ROOT, capture_output=True, timeout=40)
    assert r.returncode == 2
    assert json.loads(r.stderr)["code"] == "DUPLICATE_JSON_KEY"


def test_symlink_source_denied(tmp_path):
    source_link = tmp_path / "source.xml"
    try:
        source_link.symlink_to(SOURCE)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this runner")
    r = subprocess.run([
        sys.executable, "-m", "tools.denominator_scope_review",
        "--action", "prepare", "--source", str(source_link),
        "--expected-source-sha256", sha256(SOURCE.read_bytes()).hexdigest(),
    ], cwd=ROOT, capture_output=True, timeout=40)
    assert r.returncode == 2
    assert json.loads(r.stderr)["code"] == "INVALID_INPUT_OR_IO"
