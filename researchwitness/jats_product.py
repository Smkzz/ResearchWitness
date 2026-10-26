"""Installed JATS source-to-review workflow, not scientific error adjudication.

No network, no PDF, no LLM and no author contact. Reports and manifests are
deterministic for an unchanged installation and source. The caller controls a
trusted, quiescent output directory; this is not a hostile-filesystem sandbox.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
from typing import Any

from ._jats_files import read_regular
from ._jats_parser import MAX_SOURCE_BYTES, audit_jats_percentage_tables

REPORT_VERSION = "researchwitness.jats.audit.v1"
MANIFEST_VERSION = "researchwitness.jats.bundle.v1"
SOURCE_NAME = "source.xml"
REPORT_NAME = "report.json"
HTML_NAME = "report.html"
MANIFEST_NAME = "manifest.json"
PAYLOADS = (SOURCE_NAME, REPORT_NAME, HTML_NAME)
MAX_MANIFEST_BYTES = 64 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z", re.ASCII)
HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                       allow_nan=False) + "\n").encode("ascii")


def strict_json(data: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("Duplicate JSON key")
            output[key] = value
        return output
    value = json.loads(data, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    if type(value) is not dict:
        raise ValueError("Expected JSON object")
    return value


def implementation_files() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {
        name: digest(read_regular(root / name, 128 * 1024))
        for name in ("_jats_parser.py", "_jats_math.py", "_jats_files.py",
                     "jats_product.py", "jats_table_projection.py", "paper_document.py",
                     "paper_statistics.py", "paper_two_by_two_source.py")
    }


def make_report(source: bytes, document_id: str, source_pin_present: bool,
                *, include_structure: bool = False,
                include_odds_ratio: bool = False) -> dict[str, Any]:
    if type(document_id) is not str or IDENTIFIER.fullmatch(document_id) is None:
        raise ValueError("Invalid document identifier")
    result = audit_jats_percentage_tables(source)
    counts: Counter[str] = Counter()
    findings: list[dict[str, Any]] = []
    source_hash = digest(source)
    for index, relation in enumerate(result["results"], start=1):
        counts[relation["status"]] += 1
        findings.append({
            "finding_id": f"{source_hash[:16]}:{index}",
            "review_state": "unreviewed",
            "scientific_error_status": "not_established",
            "relationship": relation,
        })
    report = {
        "schema_version": REPORT_VERSION,
        "document": {
            "document_id": document_id,
            "source_format": "jats",
            "source_sha256": source_hash,
            "source_bytes": len(source),
            "provenance_status": "unverified_local",
            "provenance_authenticated_by_tool": False,
            "expected_hash_verified": source_pin_present,
        },
        "implementation_files": implementation_files(),
        "processing": {
            "status": "completed",
            "tables_inspected": result["tables_inspected"],
            "relationships_detected": len(findings),
            "extracted_text_sha256": result["extracted_text_sha256"],
            "extraction_profile": result["extraction_profile"],
        },
        "summary": {
            "arithmetic_matches": counts["arithmetic_match"],
            "mismatch_candidates": counts["arithmetic_mismatch_candidate"],
            "abstentions": len(findings) - counts["arithmetic_match"]
            - counts["arithmetic_mismatch_candidate"],
        },
        "findings": findings,
        "paper_error_established": False,
        "external_actions": "OUT_OF_SCOPE",
        "limitations": [
            "Only bounded source-linked arithmetic is checked; no whole-paper verdict.",
            "Source hashes verify bytes, not publisher origin.",
            "Denominator, population, adjustment and rounding ambiguity remain unresolved.",
            "PDF/OCR, sealed evaluation, network, AI providers and author contact are outside scope.",
        ],
    }
    if include_structure or include_odds_ratio:
        from .jats_table_projection import project_jats_tables
        projection = project_jats_tables(source, result)
        if include_structure:
            report["table_projection"] = projection.to_dict()
        if include_odds_ratio:
            from .paper_two_by_two_source import check_jats_unadjusted_2x2_tables
            report["odds_ratio_review"] = check_jats_unadjusted_2x2_tables(projection)
    return report


def render_html(report: dict[str, Any]) -> bytes:
    doc = report["document"]
    rows = []
    for item in report["findings"]:
        relation = item["relationship"]
        evidence = relation["evidence"]
        fields = (
            item["finding_id"], relation["status"], relation.get("reason") or "",
            str(relation.get("numerator") if relation.get("numerator") is not None else "?"),
            str(relation.get("denominator") if relation.get("denominator") is not None else "?"),
            str(relation.get("reported_percent") or ""),
            str(relation.get("contract_expected_percent") or "?"),
            str(evidence.get("cell_quote") or ""),
        )
        rows.append("<tr>" + "".join("<td>" + escape(str(x), quote=True) + "</td>"
                                     for x in fields) + "</tr>")
    headings = ("ID", "Status", "Reason", "Count", "Denominator", "Reported %", "Expected %",
                "Source excerpt")
    doc_name = escape(doc["document_id"], quote=True)
    source_hash = escape(doc["source_sha256"], quote=True)
    html = (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>ResearchWitness JATS review</title>"
        "<style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:0 1em}"
        "table{border-collapse:collapse;width:100%}td,th{padding:.5em;border:1px solid #999;"
        "vertical-align:top;overflow-wrap:anywhere}th{text-align:left}small{color:#555}</style>"
        "<h1>ResearchWitness JATS development review</h1>"
        "<p>Document: " + doc_name + "</p>"
        "<p>SHA-256: <code>" + source_hash + "</code></p>"
        "<p><strong>All findings are unreviewed candidates, not established errors.</strong></p>"
        "<table><thead><tr>" +
        "".join("<th>" + escape(x) + "</th>" for x in headings) +
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        "<p><small>Offline. No source authentication, scientific adjudication,"
        " or external action performed.</small></p></html>\n"
    )
    if "odds_ratio_review" in report:
        review = report["odds_ratio_review"]
        candidate_rows = []
        for finding in review["findings"]:
            cells = (finding["table_id"], finding["row_identity"],
                     finding["timepoint"], finding["reported_odds_ratio"],
                     finding["recomputed_at_display_precision"], finding["status"])
            candidate_rows.append("<tr>" + "".join(
                "<td>" + escape(str(value), quote=True) + "</td>"
                for value in cells
            ) + "</tr>")
        disclosure = (
            "<h2>Opt-in unadjusted 2×2 odds-ratio review</h2>"
            "<p>Only explicit source-mapped counts are considered. "
            "Every mismatch is an unreviewed arithmetic candidate.</p>"
            "<p>Scan complete: " + escape(str(review["scan_complete"])) + "</p>"
            "<table><thead><tr><th>Table</th><th>Outcome</th><th>Timepoint</th>"
            "<th>Reported OR</th><th>Recomputed OR</th><th>Status</th></tr></thead>"
            "<tbody>" + "".join(candidate_rows) + "</tbody></table>"
        )
        html = html.replace("</html>\n", disclosure + "</html>\n")
    return html.encode("utf-8")


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def audit_source(source: Path, output_dir: Path, document_id: str,
                 expected_source_sha256: str | None = None,
                 *, include_structure: bool = False,
                 include_odds_ratio: bool = False) -> dict[str, Any]:
    if (expected_source_sha256 is not None and
            (type(expected_source_sha256) is not str or
             HASH.fullmatch(expected_source_sha256) is None)):
        raise ValueError("Invalid expected source SHA-256")
    data = read_regular(Path(source), MAX_SOURCE_BYTES)
    if expected_source_sha256 is not None and digest(data) != expected_source_sha256:
        raise ValueError("Source SHA-256 differs from expected version")
    # Do all interpretation before touching output, which must be a new directory.
    report = make_report(data, document_id, expected_source_sha256 is not None,
                         include_structure=include_structure,
                         include_odds_ratio=include_odds_ratio)
    report_bytes = canonical_json(report)
    html_bytes = render_html(report)
    if len(report_bytes) > MAX_REPORT_BYTES or len(html_bytes) > MAX_REPORT_BYTES:
        raise ValueError("Review exceeds its output byte limit")
    root = Path(output_dir)
    if not root.parent.is_dir() or root.exists() or root.is_symlink():
        raise ValueError("Output parent must exist and output directory must be new")
    payloads = {SOURCE_NAME: data, REPORT_NAME: report_bytes, HTML_NAME: html_bytes}
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "document_id": document_id,
        "source_sha256": digest(data),
        "files": {name: {"sha256": digest(payload), "bytes": len(payload)}
                  for name, payload in payloads.items()},
    }
    manifest_bytes = canonical_json(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest exceeds its limit")
    root.mkdir(exist_ok=False)
    for name in PAYLOADS:
        write_new(root / name, payloads[name])
    write_new(root / MANIFEST_NAME, manifest_bytes)
    return {
        "bundle": str(root),
        "manifest_sha256": digest(manifest_bytes),
        "document_id": document_id,
        "summary": report["summary"],
        "paper_error_established": False,
        "external_actions": "OUT_OF_SCOPE",
    }


def replay_bundle(bundle: Path, expected_manifest_sha256: str | None = None) -> dict[str, Any]:
    if (expected_manifest_sha256 is not None and
            (type(expected_manifest_sha256) is not str or
             HASH.fullmatch(expected_manifest_sha256) is None)):
        raise ValueError("Invalid expected manifest SHA-256")
    root = Path(bundle)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Review bundle must be a directory")
    if {entry.name for entry in root.iterdir()} != set(PAYLOADS) | {MANIFEST_NAME}:
        raise ValueError("Missing or unexpected bundle entry")
    manifest_bytes = read_regular(root / MANIFEST_NAME, MAX_MANIFEST_BYTES)
    if expected_manifest_sha256 is not None and digest(manifest_bytes) != expected_manifest_sha256:
        raise ValueError("Manifest differs from the externally pinned hash")
    manifest = strict_json(manifest_bytes)
    if (set(manifest) != {"schema_version", "document_id", "source_sha256", "files"}
            or manifest["schema_version"] != MANIFEST_VERSION
            or type(manifest["document_id"]) is not str
            or IDENTIFIER.fullmatch(manifest["document_id"]) is None
            or type(manifest["files"]) is not dict
            or set(manifest["files"]) != set(PAYLOADS)):
        raise ValueError("Invalid JATS manifest")
    contents = {}
    for name, limit in ((SOURCE_NAME, MAX_SOURCE_BYTES), (REPORT_NAME, MAX_REPORT_BYTES),
                        (HTML_NAME, MAX_REPORT_BYTES)):
        record = manifest["files"][name]
        if (type(record) is not dict or set(record) != {"sha256", "bytes"}
                or type(record["bytes"]) is not int or not 0 <= record["bytes"] <= limit
                or type(record["sha256"]) is not str or HASH.fullmatch(record["sha256"]) is None):
            raise ValueError("Invalid payload metadata")
        contents[name] = read_regular(root / name, limit)
        if len(contents[name]) != record["bytes"] or digest(contents[name]) != record["sha256"]:
            raise ValueError("Manifested payload was modified")
    if digest(contents[SOURCE_NAME]) != manifest["source_sha256"]:
        raise ValueError("Source version changed")
    saved_report = strict_json(contents[REPORT_NAME])
    pinned_before = saved_report.get("document", {}).get("expected_hash_verified")
    if type(pinned_before) is not bool:
        raise ValueError("Invalid recorded source pin state")
    structured = "table_projection" in saved_report
    odds_ratio = "odds_ratio_review" in saved_report
    new_report = make_report(contents[SOURCE_NAME], manifest["document_id"], pinned_before,
                             include_structure=structured,
                             include_odds_ratio=odds_ratio)
    if (canonical_json(new_report) != contents[REPORT_NAME]
            or render_html(new_report) != contents[HTML_NAME]):
        raise ValueError("Independent replay disagrees with recorded result")
    return {
        "status": "verified", "bundle": str(root), "manifest_sha256": digest(manifest_bytes),
        "findings_replayed": len(new_report["findings"]), "paper_error_established": False,
        "external_actions": "OUT_OF_SCOPE",
    }
