"""Bounded offline development audits and percentage benchmark comparisons.

Run ``python -m tools.research_audit audit --help`` or ``compare --help``.
This source-checkout tool remains outside the trusted scientific verifier core.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit

from tools.audit_contracts import validate
from tools.offline_files import read_regular
from tools.jats_percentage_audit import MAX_SOURCE_BYTES, JATSSourceError, audit_jats_percentage_tables
from tools.pdf_percentage_audit import PDFSourceError, audit_pdf_percentage_tables

ROOT = Path(__file__).resolve().parents[1]
DETECTOR_PATHS = ("tools/research_audit.py", "tools/audit_contracts.py",
                  "tools/offline_files.py", "tools/jats_percentage_audit.py",
                  "tools/pdf_percentage_audit.py", "tools/public_discovery.py")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detector_files() -> dict[str, str]:
    return {name: sha((ROOT / name).read_bytes()) for name in DETECTOR_PATHS}


def safe_text(value: Any) -> str:
    """Render source content as text, including when a PDF contains Markdown/HTML."""
    text = html.escape(" ".join(str(value).split()), quote=True)
    return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", text)


def audit_document(data: bytes, *, document_id: str, input_format: str,
                   source_url: str = "", provenance_status: str = "unverified_local",
                   expected_sha256: str | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,149}", document_id):
        raise ValueError("Document identifier must be a short non-path identifier")
    if input_format not in {"jats", "pdf"}:
        raise ValueError("Input format must be jats or pdf")
    if not isinstance(data, bytes) or not data or len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Source is empty or exceeds the 8 MiB limit")
    if provenance_status not in {"unverified_local", "owner_hash_verified_handoff", "recorded_public_retrieval"}:
        raise ValueError("Unsupported provenance status")
    if len(source_url) > 2000:
        raise ValueError("Source URL is too long")
    if source_url:
        parsed = urlsplit(source_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Provenance URL must be public HTTPS metadata without credentials")
    source_hash = sha(data)
    if expected_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or source_hash != expected_sha256:
            raise ValueError("Source SHA-256 does not match the expected source version")
    if provenance_status == "owner_hash_verified_handoff" and expected_sha256 is None:
        raise ValueError("A hash-verified owner handoff requires an expected SHA-256")
    if provenance_status == "recorded_public_retrieval" and not source_url:
        raise ValueError("A recorded retrieval requires a source URL")

    reason = None
    try:
        raw = audit_jats_percentage_tables(data) if input_format == "jats" else audit_pdf_percentage_tables(data)
    except (JATSSourceError, PDFSourceError) as exc:
        raw = {"tables_inspected": 0, "results": [], "limitations": []}
        reason = str(exc)
    findings = []
    statuses: Counter[str] = Counter()
    conditional_mismatches = 0
    for index, result in enumerate(raw["results"], start=1):
        relation = copy.deepcopy(result)
        relation["evidence"]["source_sha256"] = source_hash
        state = result["status"] if result["status"] in {"arithmetic_match", "arithmetic_mismatch_candidate"} else "extracted_evidence"
        statuses[state] += 1
        conditional = relation.get("conditional_calculation", {})
        conditional_mismatches += conditional.get("arithmetic_matches") is False
        findings.append({"finding_id": f"{source_hash[:16]}:{index}", "state": state,
                         "review_state": "unreviewed", "scientific_error_status": "not_established",
                         "relationship": relation})
    report = {
        "schema_version": "research-audit.v1",
        "document": {"document_id": document_id, "source_sha256": source_hash,
                     "source_bytes": len(data), "input_format": input_format,
                     "source_url": source_url, "provenance_status": provenance_status,
                     "provenance_authenticated_by_tool": False,
                     "expected_hash_verified": expected_sha256 is not None},
        "detector_files": detector_files(),
        "processing": {"status": "extraction_failed" if reason else "completed", "reason": reason,
                       "tables_inspected": raw["tables_inspected"], "relationships_detected": len(findings),
                       "extracted_text_sha256": raw.get("extracted_text_sha256", raw.get("layout_text_sha256")),
                       "extraction_profile": raw.get("extraction_profile", "pdftotext-layout-utf8" if input_format == "pdf" else "jats-normalized-text-v1")},
        "summary": {"arithmetic_matches": statuses["arithmetic_match"],
                    "mismatch_candidates": statuses["arithmetic_mismatch_candidate"],
                    "abstentions": statuses["extracted_evidence"],
                    "conditional_mismatches": conditional_mismatches},
        "findings": findings,
        "limitations": ["Development audit only; no scientific error or protected-evaluation eligibility is established.",
                        "Source and extraction hashes verify byte integrity; provenance remains an operator assertion.",
                        "All findings remain unreviewed. Human-reviewed and independently corroborated findings require separate evidence.",
                        "Conditional calculations state assumptions; they do not resolve missing denominator scope.",
                        "Unsupported scientific relationships, layouts, and source conventions can be missed.",
                        *raw["limitations"]],
    }
    validate(report, "research-audit.v1.schema.json")
    return report


def audit_markdown(report: dict[str, Any]) -> str:
    doc, processing, summary = report["document"], report["processing"], report["summary"]
    lines = [f"# Research audit: {safe_text(doc['document_id'])}", "",
             f"Source SHA-256: `{doc['source_sha256']}`. Format: {doc['input_format']}.",
             f"Provenance assertion: {safe_text(doc['provenance_status'])}; authenticated by this tool: no.",
             f"Source URL: {safe_text(doc['source_url'] or 'not supplied')}",
             f"Processing: {processing['status']}. {safe_text(processing['reason'] or '')}",
             f"Extracted-text SHA-256: `{processing['extracted_text_sha256'] or 'not produced'}`.", "",
             f"Inspected {processing['tables_inspected']} tables; detected {processing['relationships_detected']} relationships. "
             f"Matches: {summary['arithmetic_matches']}; mismatch candidates: {summary['mismatch_candidates']}; "
             f"abstentions: {summary['abstentions']}; conditional mismatches requiring scope review: {summary['conditional_mismatches']}.", "",
             "All findings are unreviewed; scientific error status is not established.", "",
             "| Finding | Source evidence and anchor | Calculation and scope | Outcome |",
             "|---|---|---|---|"]
    for finding in report["findings"]:
        r, evidence = finding["relationship"], finding["relationship"]["evidence"]
        quote = evidence.get("relationship_quote", evidence.get("cell_quote", evidence.get("row_quote", "")))
        if "byte_start" in evidence:
            anchor = f"XML bytes [{evidence['byte_start']}, {evidence['byte_end']})"
        else:
            anchor = f"extracted page {evidence.get('page')}, line {evidence.get('line')}, chars [{evidence.get('page_text_char_start')}, {evidence.get('page_text_char_end')})"
        calculation = (f"{r['numerator']} / {r['denominator']} × 100; expected {r.get('contract_expected_percent')}%, "
                       f"reported {r['reported_percent']}%; scope {r.get('denominator_scope')}" if r.get("contract_expected_percent") is not None
                       else f"numerator {r['numerator']}; denominator {r.get('denominator')}; reported {r['reported_percent']}%; calculation withheld")
        if r.get("conditional_calculation"):
            conditional = r["conditional_calculation"]
            calculation += (f". Conditional on {conditional['assumption']}: {r['numerator']} / {conditional['denominator']} × 100 "
                            f"rounds to {conditional['rounded_percent']}%")
        lines.append(f"| {safe_text(finding['finding_id'])} | {safe_text(quote)}; {safe_text(anchor)} | {safe_text(calculation)} | {safe_text(r['status'])}: {safe_text(r.get('reason') or '')} |")
    lines += ["", "## Review requirements", "", "Resolve denominator scope, source version, weighting/adjustment, rounding conventions, and extraction fidelity before any scientific conclusion.", ""]
    lines += [f"- {safe_text(item)}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def write_reports(json_path: Path, markdown_path: Path, report: dict[str, Any], markdown: str,
                  *, protected_paths: tuple[Path, ...] = ()) -> None:
    payloads = [(json_path, json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"),
                (markdown_path, markdown)]
    resolved = [path.resolve() for path, _text in payloads]
    if len(set(resolved)) != len(resolved) or set(resolved) & {path.resolve() for path in protected_paths}:
        raise ValueError("Output paths must be distinct and must not overwrite input artifacts")
    for path, text in payloads:
        if (path.exists() or path.is_symlink()) and read_regular(path, len(text.encode("utf-8"))).decode("utf-8") != text:
            raise ValueError(f"Refusing to overwrite a different existing report: {path}")
    for path, text in payloads:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="Audit one explicitly supplied local document")
    audit.add_argument("source", type=Path)
    audit.add_argument("--document-id", required=True)
    audit.add_argument("--format", choices=["jats", "pdf"], required=True)
    audit.add_argument("--source-url", default="")
    audit.add_argument("--provenance-status", default="unverified_local",
                       choices=["unverified_local", "owner_hash_verified_handoff", "recorded_public_retrieval"])
    audit.add_argument("--expected-sha256")
    compare = sub.add_parser("compare", help="Compare supplied offline detector reports with source-bound annotations")
    compare.add_argument("--annotations", type=Path, required=True)
    compare.add_argument("--run", type=Path, action="append", required=True)
    compare.add_argument("--require-no-regression", action="store_true", help="Fail if later runs lose annotated coverage or gain incorrect denominator assignments")
    for command in (audit, compare):
        command.add_argument("--json-output", type=Path, required=True)
        command.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            data = read_regular(args.source, MAX_SOURCE_BYTES)
            report = audit_document(data, document_id=args.document_id, input_format=args.format,
                                    source_url=args.source_url, provenance_status=args.provenance_status,
                                    expected_sha256=args.expected_sha256)
            write_reports(args.json_output, args.markdown_output, report, audit_markdown(report), protected_paths=(args.source,))
            return 0 if report["processing"]["status"] == "completed" else 2
        from tools.percentage_benchmark import compare_runs, comparison_markdown, regression_failures
        report = compare_runs(args.annotations, args.run)
        write_reports(args.json_output, args.markdown_output, report, comparison_markdown(report),
                      protected_paths=(args.annotations, *args.run))
        if args.require_no_regression and regression_failures(report):
            print("Development regression gate failed: " + "; ".join(regression_failures(report)), file=sys.stderr)
            return 3
        return 0
    except (OSError, ValueError, RecursionError) as exc:
        print(f"Research audit failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
