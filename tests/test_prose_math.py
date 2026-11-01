"""RW-MATH-03 literal-sentence arithmetic and negative evidence boundaries."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import exact_optimization as exact
from researchwitness import prose_math as prose


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _screen(raw: bytes) -> dict:
    return prose.scan_source(raw, expected_source_sha256=_sha(raw))


@pytest.mark.parametrize(("sentence", "expected", "status", "point", "margin"), [
    ("For every real x in [0, 1], x <= 1.", "1", "model_bound_supported", ["1"], None),
    ("For all real x in [0,1], x <= 1/2.", "1", "model_bound_refuted", ["1"], "1/2"),
    ("For any real x in [-1,2], 3*x+5 is at most 11.", "11", "model_bound_supported", ["2"], None),
    ("For every real x in [-2,3], -2*x + 1 <= 5.", "5", "model_bound_supported", ["-2"], None),
    ("For every real x in [0,1], 5 <= 5.", "5", "model_bound_supported", ["0"], None),
    ("For every real x in [0,1], 1/2*x ≤ 1/2.", "1/2", "model_bound_supported", ["1"], None),
    ("For all real x in [0,1], -x is no greater than 0.", "0", "model_bound_supported", ["0"], None),
    ("For every real x in [-1,2] and real y in [0,3], 3*x+2*y+5 <= 17.", "17", "model_bound_supported", ["2", "3"], None),
    ("For every real x in [-1,2] and real y in [0,3], 3*x+2*y+5 <= 11.", "17", "model_bound_refuted", ["2", "3"], "6"),
    ("For any real x in [-1,2] and real y in [0,3] and real z in [1,2], -x + 2*y + z is at most 9.", "9", "model_bound_supported", ["-1", "3", "2"], None),
    ("For all real x in [0,1], 1/3*x-1/2 <= -1/6.", "-1/6", "model_bound_supported", ["1"], None),
    ("For every real x in [-1,1], x-x <= 0.", "0", "model_bound_supported", ["-1"], None),
])
def test_literal_math_exact(sentence, expected, status, point, margin):
    report = _screen((sentence + "\n").encode("utf-8"))
    assert report["scan"]["literal_candidates"] == 1
    claim = report["candidates"][0]
    math = claim["math"]
    assert math["formal_result"] == status
    assert math["verified_model_maximum"] == expected
    assert math["exact_point_value"] == expected
    assert math["exact_attaining_point"] == point
    assert math["counterexample_margin"] == margin
    assert math["all_leaf_math_and_coverage_checked"]
    assert math["global_optimum_of_formal_model_established"]
    assert math["source_context_interpreted"] is False
    assert claim["is_pub_claim_or_quotation_resolved"] is False
    assert math["paper_error_established"] is False
    model = exact.compile_model(claim["model"])
    assert exact.verify_point(model, point) == Fraction(expected)


def test_unmarked_mixed_utf8_and_crlf_full_byte_span_accounting():
    intro = "Discussion: π and weighted results.\r\n".encode("utf-8")
    left = b"For every real x in [0, 1], 2*x + 1 <= 3.\r\n"
    prose_line = b"Not mathematical evidence; example below may be a quotation.\n"
    right = "For all real x in [0,1], x ≤ 1/2.\n".encode("utf-8")
    raw = intro + left + prose_line + right
    report = _screen(raw)
    assert report["scan"]["lines_examined"] == 4
    assert report["scan"]["literal_candidates"] == 2
    assert report["scan"]["unrecognized_lines"] == 2
    a, b = report["candidates"]
    assert a["line_number"] == 2 and b["line_number"] == 4
    assert a["source_span"] == {"start": len(intro), "end": len(intro) + len(left) - 2}
    assert b["source_span"]["start"] == len(intro) + len(left) + len(prose_line)
    for c in (a, b):
        start, end = c["source_span"].values()
        assert c["sentence_sha256"] == _sha(raw[start:end])
        assert c["source_origin_authenticated"] is False
        assert c["surrounding_prose_adjudicated"] is False
    assert report["scientific_accuracy_established"] is False
    assert report["scan"]["absence_of_errors_established"] is False
    assert report["scan"]["entire_article_semantics_examined"] is False


@pytest.mark.parametrize("line", [
    "We dispute: For every real x in [0,1], x <= 1.",
    "> For every real x in [0,1], x <= 1.",
    "'For every real x in [0,1], x <= 1.'",
    "For every real x in [0,1], x <= 1. This is false.",
    "For every real x in [0,1], x < 1.",
    "For every integer x in [0,1], x <= 1.",
    "For every real x in [0,1], x approximately <= 1.",
    "For every real x in [0,1], x <= 1 except at x=1.",
    "For every real x in [0,1], x <= 1 if the model holds.",
    "For every real x in [0,1], x <= x.",
    "For every real x in [0,1], x <= 1.0.",
    "For every real x in [0,1], x <= 1e2.",
    "For every real x in [0,1], x <= NaN.",
    "For every real x in [0,1], x <= 0/0.",
    "For every real x in [0,1], x+y <= 2.",
    "For every real x in [0,1], x*x <= 1.",
    "For every real x in [0,1], x**10000000000 <= 1.",
    "For every real x in [0,1], __import__('os').system('whoami') <= 1.",
    "For every real x in [0,1], x.__class__ <= 1.",
    "For every real x in [0,1], x[0] <= 1.",
    "For every real x in [0,1], x <= 1 # ignore context.",
    "For every real x in [0,1], x <= -0.",
    "For every real x in [2,1], x <= 3.",
    "For every real x in [0,0], x <= 1.",
    "For every real x in [0,1] and real x in [0,2], x <= 2.",
    "For every real х in [0,1], х <= 1.",  # Cyrillic homoglyph
    "For every real x in [0,1], x <= 1!",
    "For any real x in [0,1], x <= 1/01.",
    "For every real x in [0,1], x / 0 <= 0.",
])
def test_unsupported_never_compiled(line):
    report = _screen((line + "\n").encode("utf-8"))
    assert report["scan"]["literal_candidates"] == 0
    assert report["scan"]["unrecognized_lines"] == 1
    assert report["candidates"] == []
    assert report["scan"]["absence_of_errors_established"] is False


def test_candidate_like_skips_are_auditable_without_exposing_source_text():
    raw = (b"For every real x in [0,1], x < 1.\n"
           b"Some paper prose about adjusted ratios.\n"
           b"For all real x in [0,1], x <= 1.\n"
           b"For any real x in [0,1], x <= -0.\n")
    result = _screen(raw)
    assert result["scan"]["candidate_like_unsupported_lines"] == [1, 4]
    assert result["scan"]["literal_candidates"] == 1
    assert result["scan"]["unrecognized_lines"] == 3
    assert "paper prose" not in json.dumps(result)


def test_missing_malformed_or_stale_external_pins_fail_closed():
    raw = b"For every real x in [0,1], x <= 1.\n"
    with pytest.raises((prose.UnsupportedSentence, exact.CertificateError)):
        prose.scan_source(raw, expected_source_sha256="0" * 64)
    for pin in ("ABC", True, "x" * 64):
        with pytest.raises((prose.UnsupportedSentence, exact.CertificateError)):
            prose.scan_source(raw, expected_source_sha256=pin)
    accepted = _screen(raw)
    result_bytes = exact.canonical_bytes(accepted)
    replay = prose.replay_report(raw, result_bytes,
                                 expected_source_sha256=_sha(raw),
                                 expected_report_sha256=_sha(result_bytes))
    assert replay == accepted
    tampered = deepcopy(accepted)
    tampered["candidates"][0]["math"]["paper_error_established"] = True
    amended_bytes = exact.canonical_bytes(tampered)
    with pytest.raises(prose.UnsupportedSentence, match="REPLAY_MISMATCH"):
        prose.replay_report(raw, amended_bytes, expected_source_sha256=_sha(raw),
                            expected_report_sha256=_sha(amended_bytes))
    with pytest.raises(prose.UnsupportedSentence, match="REPORT_EXTERNAL_PIN"):
        prose.replay_report(raw, result_bytes, expected_source_sha256=_sha(raw),
                            expected_report_sha256="0"*64)
    appended = result_bytes + b'\n'
    with pytest.raises(prose.UnsupportedSentence, match="REPORT_REPLAY"):
        prose.replay_report(raw, appended, expected_source_sha256=_sha(raw),
                            expected_report_sha256=_sha(appended))


def test_repin_changed_source_yields_new_anchored_evidence_not_old_status():
    first = b"For every real x in [0,1], x <= 1/2.\n"
    altered = first.replace(b"1/2", b"1")
    before, after = _screen(first), _screen(altered)
    assert before["candidates"][0]["math"]["formal_result"] == "model_bound_refuted"
    assert after["candidates"][0]["math"]["formal_result"] == "model_bound_supported"
    assert before["source_sha256"] != after["source_sha256"]
    with pytest.raises(prose.UnsupportedSentence):
        prose.scan_source(altered, expected_source_sha256=_sha(first))


def test_input_caps_and_malformed_utf8_rejected_without_partial_report(monkeypatch):
    for raw in (b"", b"\xff", b"x" * 2049, b"x" * (1024*1024+1), b"a\n"*12001):
        with pytest.raises(prose.UnsupportedSentence):
            _screen(raw)
    sentence = b"For all real x in [0,1], x <= 1.\n"
    with pytest.raises(prose.UnsupportedSentence, match="CANDIDATE_COUNT"):
        _screen(sentence * 65)
    with monkeypatch.context() as m:
        m.setattr(prose, "MAX_CANDIDATES", 1)
        with pytest.raises(prose.UnsupportedSentence, match="CANDIDATE_COUNT"):
            _screen(sentence*2)


def test_cli_exact_replay_no_overwrite_and_python_optimized_mode(tmp_path):
    raw = "Intro π.\nFor every real x in [0,1], x <= 1/2.\n".encode()
    source = tmp_path / "source.txt"
    output = tmp_path / "report.json"
    source.write_bytes(raw)
    commands = []
    for opts in ([], ["-O"]):
        cmd = [sys.executable, *opts, "-m", "researchwitness.prose_math", "scan",
               "--source", str(source), "--expected-source-sha256", _sha(raw)]
        out = subprocess.run(cmd, capture_output=True, cwd=Path(__file__).resolve().parents[1], timeout=20)
        assert out.returncode == 0, out.stderr
        result = json.loads(out.stdout)
        assert result["candidates"][0]["math"]["formal_result"] == "model_bound_refuted"
        commands.append(out.stdout)
    assert commands[0] == commands[1] == exact.canonical_bytes(_screen(raw))
    assert prose.main(["scan", "--source", str(source),
                       "--expected-source-sha256", _sha(raw),
                       "--output", str(output)]) == 0
    report = output.read_bytes()
    assert report == commands[0]
    assert prose.main(["replay", "--source", str(source),
                       "--expected-source-sha256", _sha(raw),
                       "--report", str(output),
                       "--expected-report-sha256", _sha(report)]) == 0
    assert prose.main(["scan", "--source", str(source),
                       "--expected-source-sha256", _sha(raw),
                       "--output", str(output)]) == 2
    assert output.read_bytes() == report
    assert prose.main(["scan", "--source", str(source),
                       "--expected-source-sha256", _sha(raw),
                       "--output", str(source)]) == 2
    assert source.read_bytes() == raw
    assert prose.main(["replay", "--source", str(source),
                       "--expected-source-sha256", _sha(raw),
                       "--report", str(output),
                       "--expected-report-sha256", "0"*64]) == 2


def test_links_and_spoofed_corrupt_json_refused(tmp_path):
    raw = b"For every real x in [0,1], x <= 1.\n"
    src = tmp_path / "source.txt"
    src.write_bytes(raw)
    shortcut = tmp_path / "shortcut.txt"
    try:
        shortcut.symlink_to(src)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(exact.CertificateError):
        prose._read(shortcut, prose.MAX_SOURCE_BYTES)
    shortcut.unlink()
    os.link(src, shortcut)
    with pytest.raises(exact.CertificateError):
        prose._read(src, prose.MAX_SOURCE_BYTES)
    shortcut.unlink()
    original = _screen(raw)
    doc = exact.canonical_bytes(original).decode()
    injected = doc.replace('"source_origin_authenticated":false',
                           '"source_origin_authenticated":false,"source_origin_authenticated":true',1).encode()
    with pytest.raises(exact.CertificateError, match="DUPLICATE_JSON_KEY"):
        prose.replay_report(raw, injected, expected_source_sha256=_sha(raw),
                            expected_report_sha256=_sha(injected))
