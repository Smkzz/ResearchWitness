"""RW-MATH-04 synthetic source-role, proof identity and adversarial regressions."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import exact_optimization as exact
from researchwitness import prose_attribution as attrib
from researchwitness import prose_math as prose

FALSE = b"For all real x in [0,1], x <= 1/2."
TRUE = b"For all real x in [0,1], x <= 1."
ROLES = ("asserted", "quoted", "negated", "hypothetical", "corrected")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def block(ident="a", role="asserted", literal=FALSE, newline=b"\n") -> bytes:
    return (
        f"RW-MATH-CONTEXT-BEGIN v1 id={ident} role={role}".encode() + newline
        + literal + newline
        + f"RW-MATH-CONTEXT-END v1 id={ident}".encode() + newline
    )


def scan(source: bytes) -> dict:
    return attrib.attribute_source(source, expected_source_sha256=sha(source))


def test_same_false_sentence_declared_assertion_versus_quotation():
    source = b"Synthetic context test only.\n" + block("claim", "asserted") + block("quote", "quoted")
    result = scan(source)
    assert result["context_block_count"] == 2
    assert result["unattributed_literal_count"] == 0
    a, b = result["context_blocks"]
    assert a["math"] == b["math"]
    assert a["model"] == b["model"]
    assert a["math"]["formal_result"] == "model_bound_refuted"
    assert a["math"]["verified_model_maximum"] == "1"
    assert a["math"]["counterexample_margin"] == "1/2"
    assert a["interpretation"] == "declared_asserted_literal_refuted"
    assert b["interpretation"] == "declared_quoted_literal_refuted"
    for item in (a, b):
        assert item["paper_error_established"] is False
        assert item["author_intent_authenticated"] is False
        assert item["publisher_source_authenticated"] is False
        assert item["context_role_is_source_declaration_only"] is True
        assert item["surrounding_prose_adjudicated"] is False
        assert item["literal_sentence_sha256"] == sha(FALSE)
        span = item["literal_source_span"]
        assert source[span["start"]:span["end"]] == FALSE
    assert result["whole_paper_meaning_verified"] is False
    assert result["scientific_accuracy_established"] is False
    assert result["external_actions"] == "NONE"


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("literal,ending", [(FALSE, "refuted"), (TRUE, "supported")])
def test_roles_do_not_modify_mathematical_verdict(role, literal, ending):
    data = scan(block("example", role, literal))
    item = data["context_blocks"][0]
    assert item["interpretation"] == f"declared_{role}_literal_{ending}"
    assert item["math"]["formal_result"] == f"model_bound_{ending}"
    assert item["math"]["paper_error_established"] is False
    assert data["paper_error_established"] is False


def test_all_five_roles_same_mathematics():
    source = b"".join(block(f"r{i}", role) for i, role in enumerate(ROLES))
    items = scan(source)["context_blocks"]
    assert len(items) == 5
    assert len({json.dumps(x["math"], sort_keys=True) for x in items}) == 1
    assert len({x["interpretation"] for x in items}) == 5


def test_unmarked_mathematics_remains_unattributed_and_unchanged():
    source = FALSE + b"\n" + block("claim") + TRUE + b"\n"
    result = scan(source)
    assert result["context_block_count"] == 1
    assert result["unattributed_literal_count"] == 2
    assert [x["line_number"] for x in result["unattributed_literal_spans"]] == [1, 5]
    assert result["context_blocks"][0]["literal_line_number"] == 3
    assert scan(FALSE + b"\n")["context_blocks"] == []
    assert scan(FALSE + b"\n")["unattributed_literal_count"] == 1
    baseline = prose.scan_source(source, expected_source_sha256=sha(source))
    assert baseline["scan"]["literal_candidates"] == 3


def test_multibyte_utf8_crlf_and_mixed_newlines_preserve_half_open_bytes():
    head = "Intro: π and α – not a claim.\r\n".encode("utf-8")
    source = head + block("c1", "quoted", newline=b"\r\n") + b"Trailing context.\n"
    result = scan(source)
    item = result["context_blocks"][0]
    assert item["begin_marker_span"]["start"] == len(head)
    for key, prefix in (("begin_marker", b"RW-MATH-CONTEXT-BEGIN"),
                        ("literal_source", FALSE),
                        ("end_marker", b"RW-MATH-CONTEXT-END")):
        span = item[key + "_span"]
        assert source[span["start"]:span["end"]].startswith(prefix)
    assert item["literal_line_number"] == 3
    assert result["source_sha256"] == sha(source)


@pytest.mark.parametrize("source,code", [
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n" + FALSE + b"\n", "UNCLOSED"),
    (b"RW-MATH-CONTEXT-END v1 id=a\n", "UNMATCHED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n"
     + FALSE + b"\nRW-MATH-CONTEXT-END v1 id=b\n", "MISMATCHED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n"
     + b"RW-MATH-CONTEXT-BEGIN v1 id=b role=quoted\n" + FALSE
     + b"\nRW-MATH-CONTEXT-END v1 id=b\nRW-MATH-CONTEXT-END v1 id=a\n", "NESTED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n"
     + FALSE + b"\n" + TRUE + b"\nRW-MATH-CONTEXT-END v1 id=a\n", "MORE_THAN_ONE"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n"
     + b"RW-MATH-CONTEXT-END v1 id=a\n", "WITHOUT_LITERAL"),
    (block("same") + block("same", "quoted"), "DUPLICATE_CONTEXT_ID"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n"
     + b"> " + FALSE + b"\nRW-MATH-CONTEXT-END v1 id=a\n", "UNSUPPORTED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n"
     + b"For every real x in [0,1], x approximately <= 1.\n"
     + b"RW-MATH-CONTEXT-END v1 id=a\n", "UNSUPPORTED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n"
     + b"This sentence is unqualified.\nRW-MATH-CONTEXT-END v1 id=a\n", "UNSUPPORTED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=unknown\n" + FALSE
     + b"\nRW-MATH-CONTEXT-END v1 id=a\n", "MALFORMED"),
    (b"RW-MATH-CONTEXT-BEGIN v2 id=a role=quoted\n" + FALSE
     + b"\nRW-MATH-CONTEXT-END v1 id=a\n", "MALFORMED"),
    (b" RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted\n" + FALSE
     + b"\nRW-MATH-CONTEXT-END v1 id=a\n", "MALFORMED"),
    (b"# RW-MATH-CONTEXT-BEGIN v1 id=a role=quoted\n" + FALSE
     + b"\nRW-MATH-CONTEXT-END v1 id=a\n", "MALFORMED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=A role=asserted\n" + FALSE
     + b"\nRW-MATH-CONTEXT-END v1 id=A\n", "MALFORMED"),
    (b"RW-MATH-CONTEXT-BEGIN v1 id=a role=quoted extra=true\n" + FALSE
     + b"\nRW-MATH-CONTEXT-END v1 id=a\n", "MALFORMED"),
    (b"RW-MATH-CONTEXT-END v1 id=a extra=true\n", "MALFORMED"),
])
def test_adversarial_declarations_fail_closed(source, code):
    with pytest.raises(attrib.AttributionError, match=code):
        scan(source)


def test_marker_in_quotation_is_not_authority():
    source = b'Example says "RW-MATH-CONTEXT-BEGIN v1 id=a role=asserted".\n'
    with pytest.raises(attrib.AttributionError, match="MALFORMED"):
        scan(source)


def test_stale_source_version_or_role_edit_rejected():
    source = block("a", "quoted")
    changed = source.replace(b"role=quoted", b"role=asserted")
    with pytest.raises(attrib.AttributionError, match="EXTERNAL_SOURCE"):
        attrib.attribute_source(changed, expected_source_sha256=sha(source))
    with pytest.raises(exact.CertificateError):
        attrib.attribute_source(source, expected_source_sha256="X" * 64)
    first, second = scan(source), scan(changed)
    assert first["source_sha256"] != second["source_sha256"]
    assert first["context_blocks"][0]["math"] == second["context_blocks"][0]["math"]


def test_report_replay_rejects_re_pinned_semantic_tampering():
    source = block("a", "quoted")
    report = exact.canonical_bytes(scan(source))
    assert attrib.replay_report(source, report, expected_source_sha256=sha(source),
                                expected_report_sha256=sha(report)) == scan(source)
    edited = deepcopy(scan(source))
    edited["context_blocks"][0]["declared_role"] = "asserted"
    altered = exact.canonical_bytes(edited)
    with pytest.raises(attrib.AttributionError, match="REPORT_REPLAY"):
        attrib.replay_report(source, altered, expected_source_sha256=sha(source),
                             expected_report_sha256=sha(altered))
    edited["context_blocks"][0]["paper_error_established"] = True
    altered = exact.canonical_bytes(edited)
    with pytest.raises(attrib.AttributionError, match="REPORT_REPLAY"):
        attrib.replay_report(source, altered, expected_source_sha256=sha(source),
                             expected_report_sha256=sha(altered))
    with pytest.raises(attrib.AttributionError, match="EXTERNAL_REPORT_PIN"):
        attrib.replay_report(source, report, expected_source_sha256=sha(source),
                             expected_report_sha256="0" * 64)


def test_recomputed_hash_does_not_sanitize_corrupt_report():
    source = block("a")
    encoded = exact.canonical_bytes(scan(source))
    injected = encoded.replace(b'"paper_error_established":false',
                               b'"paper_error_established":false,"paper_error_established":true', 1)
    with pytest.raises(exact.CertificateError, match="DUPLICATE_JSON_KEY"):
        attrib.replay_report(source, injected, expected_source_sha256=sha(source),
                             expected_report_sha256=sha(injected))
    for altered in (encoded + b"\n", encoded.rstrip(b"\n"), encoded + b"{}"):
        with pytest.raises((attrib.AttributionError, exact.CertificateError)):
            attrib.replay_report(source, altered, expected_source_sha256=sha(source),
                                 expected_report_sha256=sha(altered))


def test_limits_and_malformed_utf8_fail_without_partial_result(monkeypatch):
    for source in (b"", b"\xff", b"a" * (attrib.MAX_SOURCE_BYTES + 1)):
        with pytest.raises((prose.UnsupportedSentence, attrib.AttributionError)):
            scan(source)
    with pytest.raises(prose.UnsupportedSentence):
        scan(block("a") * 65)
    with monkeypatch.context() as patch:
        patch.setattr(attrib, "MAX_BLOCKS", 1)
        with pytest.raises(attrib.AttributionError, match="CONTEXT_BLOCK_LIMIT"):
            scan(block("a") + block("b"))
    with pytest.raises(prose.UnsupportedSentence, match="CANDIDATE_COUNT_LIMIT"):
        scan((FALSE + b"\n") * 65 + block("a"))


def test_unsafe_literal_rejected_even_if_asserted():
    with pytest.raises(attrib.AttributionError, match="UNSUPPORTED"):
        scan(block("a", "asserted", b"For all real x in [0,1], x*x <= 1."))


def test_cli_scan_replay_no_overwrite_and_optimized_mode(tmp_path):
    source = b"Intro: \xcf\x80.\n" + block("a", "asserted") + block("b", "quoted")
    path, report = tmp_path / "source.txt", tmp_path / "report.json"
    path.write_bytes(source)
    results = []
    root = Path(__file__).resolve().parents[1]
    for options in ([], ["-O"]):
        cmd = [sys.executable, *options, "-m", "researchwitness.prose_attribution", "scan",
               "--source", str(path), "--expected-source-sha256", sha(source)]
        outcome = subprocess.run(cmd, cwd=root, capture_output=True, timeout=20)
        assert outcome.returncode == 0, outcome.stderr
        results.append(outcome.stdout)
    assert results[0] == results[1] == exact.canonical_bytes(scan(source))
    assert attrib.main(["scan", "--source", str(path),
                        "--expected-source-sha256", sha(source),
                        "--output", str(report)]) == 0
    encoded = report.read_bytes()
    assert encoded == results[0]
    assert attrib.main(["replay", "--source", str(path),
                        "--expected-source-sha256", sha(source),
                        "--report", str(report),
                        "--expected-report-sha256", sha(encoded)]) == 0
    assert attrib.main(["scan", "--source", str(path),
                        "--expected-source-sha256", sha(source),
                        "--output", str(report)]) == 2
    assert attrib.main(["scan", "--source", str(path),
                        "--expected-source-sha256", sha(source),
                        "--output", str(path)]) == 2
    assert path.read_bytes() == source and report.read_bytes() == encoded


def test_linked_source_rejected(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(block("a"))
    link = tmp_path / "alias"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not available")
    with pytest.raises(exact.CertificateError):
        attrib._read(link, attrib.MAX_SOURCE_BYTES)
    link.unlink()
    os.link(source, link)
    with pytest.raises(exact.CertificateError):
        attrib._read(source, attrib.MAX_SOURCE_BYTES)


def test_unmarked_prose_has_no_inferred_authorial_role():
    source = b"The following is an invented false quotation.\n" + FALSE + b"\n"
    result = scan(source)
    assert result["context_blocks"] == []
    assert result["unattributed_literal_count"] == 1
    assert result["whole_paper_meaning_verified"] is False
    assert result["paper_error_established"] is False
