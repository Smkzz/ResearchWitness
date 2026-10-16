"""Synthetic real-runtime PDF smoke checks; never a sandbox qualification claim.

Requires an operator-reviewed local image and the existing strict extraction
runner. No image pull, daemon recovery, host Poppler, or network path exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.pdf_percentage_audit import PDFSourceError, _extract_layout_text, parse_pdf_layout_text


def synthetic_pdf(lines: list[str]) -> bytes:
    """Construct a deterministic one-page PDF without executing a PDF parser."""
    if len(lines) > 100 or any(len(line) > 200 or not line.isascii() for line in lines):
        raise ValueError("Synthetic PDF fixture text exceeds its bounds")
    commands = [b"BT /F1 10 Tf 40 780 Td"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(("(" + escaped + ") Tj 0 -15 Td").encode("ascii"))
    commands.append(b"ET")
    stream = b"\n".join(commands) + b"\n"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream"]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def normal_report_matches(report: dict[str, Any], data: bytes, text: str) -> bool:
    source_hash = hashlib.sha256(data).hexdigest()
    text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if (report.get('source_sha256') != source_hash or report.get('layout_text_sha256') != text_hash
            or report.get('tables_inspected') != 1 or report.get('percentage_cells_reviewed') != 2):
        return False
    results = report.get('results', [])
    if len(results) != 2:
        return False
    for r, label, percentage, status in zip(results, ['A', 'B'], ['10.0', '11.0'],
            ['arithmetic_match', 'arithmetic_mismatch_candidate']):
        if any(r.get(key) != value for key, value in {'numerator': 4, 'denominator': 40,
                'reported_percent': percentage, 'contract_expected_percent': '10.0',
                'exact_ratio_percent': '400/40', 'display_precision': 1, 'status': status}.items()):
            return False
        evidence = r.get('evidence', {})
        if (evidence.get('source_pdf_sha256') != source_hash or evidence.get('layout_text_sha256') != text_hash
                or evidence.get('page') != 1 or evidence.get('row_label') != label):
            return False
        page = text.split('\f')[0]
        for a in [evidence, *evidence.get('table_header_denominator_sources', [])]:
            start, end = a.get('page_text_char_start'), a.get('page_text_char_end')
            quote = a.get('row_quote', a.get('quote'))
            if (a.get('page') != 1 or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(page) or page[start:end].strip() != quote):
                return False
        if not evidence.get('table_header_denominator_sources'):
            return False
    return True


def smoke_checks() -> dict[str, Any]:
    fixtures = [("normal", synthetic_pdf(["Table 1: Synthetic", "Count (%) N=40", "A 4 (10.0)", "B 4 (11.0)"]), "two_relationships"),
                ("malformed", b"%PDF-1.4\ninvalid synthetic fixture\n", "extraction_failure"),
                ("unsupported_empty_page", synthetic_pdf([]), "extraction_failure")]
    results = []
    for name, data, expected in fixtures:
        try:
            text = _extract_layout_text(data)
            report = parse_pdf_layout_text(text, hashlib.sha256(data).hexdigest())
            passed = expected == "two_relationships" and normal_report_matches(report, data, text)
            results.append({"fixture": name, "source_sha256": hashlib.sha256(data).hexdigest(),
                "expected": expected, "passed": passed, "report": report})
        except PDFSourceError as exc:
            # A first-fixture failure is an infrastructure/extraction blocker.
            # Never continue to retry the same unavailable runtime.
            expected_reason = {"malformed": "Isolated Poppler could not extract this PDF",
                "unsupported_empty_page": "PDF has no extractable text; OCR is not supported"}.get(name)
            passed = expected_reason is not None and str(exc) == expected_reason
            results.append({"fixture": name, "source_sha256": hashlib.sha256(data).hexdigest(),
                "expected": expected, "passed": passed, "reason": str(exc)})
            if not passed:
                break
        if not results[-1]["passed"]:
            break
    complete = len(results) == len(fixtures) and all(r["passed"] for r in results)
    return {"schema_version": 1, "status": "smoke_passed_not_qualified" if complete else "blocked_or_failed",
        "sandbox_qualified": False, "results": results,
        "remaining_qualification": ["Independent image rootfs/package/provenance review and pinned image ID",
            "Effective runtime isolation, environment and mount inspection on the authorized daemon",
            "Real resource-limit/timeout/output-overflow and success/failure cleanup evidence",
            "Separate hermetic failure-injection tests do not establish real runtime enforcement"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = smoke_checks()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return 0 if report["status"] == "smoke_passed_not_qualified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
