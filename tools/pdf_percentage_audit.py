"""Conservative, offline percentage review for text-based PDF tables.

This development aid uses Poppler's ``pdftotext -layout`` for extraction. It
does not authenticate a PDF, perform OCR, or decide whether a paper is wrong.
Its layout heuristics only surface arithmetic candidates for human review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Event, Thread
from typing import Any

from tools.public_discovery import percentage_recalculation
from tools.offline_files import read_regular

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_LAYOUT_TEXT_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_TABLES = 200
MAX_RESULTS = 1_000
MAX_EVIDENCE_TEXT = 500
EXTRACTION_TIMEOUT_SECONDS = 20
SANDBOX_IMAGE_ENV = "RESEARCHWITNESS_PDF_SANDBOX_IMAGE"
SANDBOX_MEMORY = "512m"
SANDBOX_TMPFS = "32m"

_PDF_SIGNATURE = b"%PDF-"
_SOURCE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_TABLE_TITLE_RE = re.compile(r"\b(?:supplementary\s+)?table\s+(?:s)?\d+\b", re.IGNORECASE)
_DENOMINATOR_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:n|N)\s*[=:]\s*([0-9]{1,9})"
    r"(?!(?:[0-9]|[.,/][0-9]|-[0-9]|[A-Za-z]))"
)
_HEADER_CUE_RE = re.compile(
    r"\b(?:number\s+of\s+[a-z][a-z-]{2,20}|count|percent(?:age)?)\b"
    r"|\bn\s*\(\s*%|%",
    re.IGNORECASE,
)
_EXPLICIT_PERCENT_RE = re.compile(r"%|\bpercent(?:age)?\b", re.IGNORECASE)
_ROW_SPECIFIC_RATIO_RE = re.compile(r"\bn\s*\(\s*%\s*[^)]*\bn\s*/\s*n\b", re.IGNORECASE)
_COUNT_PERCENT_LINE_RE = re.compile(
    r"^\s*(?P<label>.+?)\s+(?P<count>[0-9]{1,9})\s*\(\s*"
    r"(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*(?P<symbol>%?)\s*\)\s*$"
)
_ROUNDING_NOTE_RE = re.compile(r"\b(?:round(?:ed|ing)?|truncat(?:e|ed|ion))\b", re.IGNORECASE)
_ADJUSTMENT_NOTE_RE = re.compile(
    r"(?:\b(?:adjusted|weighted|standardized|standardised)\b.{0,120}"
    r"\b(?:percent(?:age)?|frequenc(?:y|ies)|proportion|rate)\b|"
    r"\b(?:percent(?:age)?|frequenc(?:y|ies)|proportion|rate)\b.{0,120}"
    r"\b(?:adjusted|weighted|standardized|standardised)\b)",
    re.IGNORECASE,
)
_TABLE_END_RE = re.compile(r"^\s*(?:legends?|footnotes?|notes?)\s*:", re.IGNORECASE)


class PDFSourceError(ValueError):
    """The PDF is unsupported, malformed for extraction, or outside limits."""


def _remove_sandbox_container(
    docker_prefix: list[str], docker_env: dict[str, str], container_id_file: Path
) -> None:
    try:
        container_id = container_id_file.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise PDFSourceError("Could not verify isolated Poppler container ID for cleanup") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", container_id):
        raise PDFSourceError("Could not verify isolated Poppler container ID for cleanup")
    try:
        result = subprocess.run(
            [*docker_prefix, "container", "rm", "--force", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=docker_env,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PDFSourceError("Could not confirm isolated Poppler container cleanup") from exc
    stderr = str(result.stderr or "").lower()
    if result.returncode != 0 and "no such container" not in stderr:
        raise PDFSourceError("Could not confirm isolated Poppler container cleanup")


def _extract_layout_text(data: bytes) -> str:
    image = os.environ.get(SANDBOX_IMAGE_ENV, "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise PDFSourceError(
            "PDF extraction requires a locally provisioned, SHA-256-pinned "
            "Poppler sandbox image"
        )

    docker = shutil.which("docker")
    if docker is None:
        raise PDFSourceError("Docker is required for isolated PDF extraction")

    # Do not load credentials, proxy settings, contexts, or proxy configuration
    # from the calling user's Docker client configuration.  The only host API
    # endpoint accepted by this runner is the local Unix socket.
    docker_env = {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"}
    with tempfile.TemporaryDirectory(prefix="researchwitness-docker-config-") as config_dir:
        docker_prefix = [
            docker,
            "--host", "unix:///var/run/docker.sock",
            "--config", config_dir,
        ]
        try:
            security_check = subprocess.run(
                [*docker_prefix, "info", "--format", "{{json .SecurityOptions}}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                env=docker_env,
                shell=False,
            )
            security_options = (
                json.loads(security_check.stdout)
                if security_check.returncode == 0
                else None
            )
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise PDFSourceError("Could not verify Docker's default seccomp profile") from exc
        if (
            not isinstance(security_options, list)
            or "name=seccomp,profile=builtin" not in security_options
        ):
            raise PDFSourceError("Docker's built-in default seccomp profile is unavailable")

        try:
            image_check = subprocess.run(
                [*docker_prefix, "image", "inspect", image, "--format", "{{.Id}}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                env=docker_env,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PDFSourceError("Could not verify the isolated Poppler sandbox image") from exc
        if image_check.returncode != 0 or image_check.stdout.strip() != image:
            raise PDFSourceError("The configured Poppler sandbox image is unavailable or unverified")
        try:
            config_check = subprocess.run(
                [*docker_prefix, "image", "inspect", image, "--format", "{{json .Config}}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                env=docker_env,
                shell=False,
            )
            image_config = json.loads(config_check.stdout) if config_check.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise PDFSourceError("Could not verify the isolated Poppler sandbox image configuration") from exc
        if (
            not isinstance(image_config, dict)
            or image_config.get("Env") not in (None, [])
            or image_config.get("Entrypoint") not in (None, [])
            or image_config.get("Volumes") not in (None, {})
        ):
            raise PDFSourceError(
                "The Poppler sandbox image must have no baked environment, entrypoint, or volumes"
            )

        container_id_file = Path(config_dir) / "container-id"
        command = [
            *docker_prefix,
            "run", "--pull=never", "--interactive", "--cidfile", str(container_id_file),
            "--network", "none",
            "--read-only",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--memory", SANDBOX_MEMORY,
            "--memory-swap", SANDBOX_MEMORY,
            "--cpus", "1",
            "--pids-limit", "8",
            "--ulimit", "cpu=20:20",
            "--ulimit", "fsize=2097152:2097152",
            "--ulimit", "nofile=64:64",
            "--ulimit", "core=0:0",
            "--tmpfs", f"/tmp:rw,nosuid,nodev,noexec,size={SANDBOX_TMPFS},mode=1777",
            "--env", "PATH=/usr/bin:/bin",
            "--env", "LANG=C",
            "--env", "LC_ALL=C",
            "--env", "HOME=/tmp",
            "--env", "TMPDIR=/tmp",
            "--workdir", "/tmp",
            "--env", "HTTP_PROXY=",
            "--env", "HTTPS_PROXY=",
            "--env", "ALL_PROXY=",
            "--env", "NO_PROXY=",
            "--env", "FTP_PROXY=",
            "--env", "http_proxy=",
            "--env", "https_proxy=",
            "--env", "all_proxy=",
            "--env", "no_proxy=",
            "--env", "ftp_proxy=",
            image,
            "/usr/bin/pdftotext", "-layout", "-enc", "UTF-8", "-", "-",
        ]

        output = bytearray()
        exceeded_limit = Event()
        with tempfile.TemporaryFile() as pdf_input:
            pdf_input.write(data)
            pdf_input.seek(0)
            try:
                process = subprocess.Popen(
                    command,
                    stdin=pdf_input,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    env=docker_env,
                )
            except OSError as exc:
                raise PDFSourceError("Could not start the isolated Poppler sandbox") from exc
            reader: Thread | None = None
            try:
                if process.stdout is None:
                    raise PDFSourceError("Isolated Poppler output pipe was unavailable")

                def drain_stdout() -> None:
                    assert process.stdout is not None
                    while True:
                        remaining = MAX_LAYOUT_TEXT_BYTES + 1 - len(output)
                        if remaining <= 0:
                            exceeded_limit.set()
                            process.kill()
                            return
                        chunk = process.stdout.read(min(64 * 1024, remaining))
                        if not chunk:
                            return
                        output.extend(chunk)
                        if len(output) > MAX_LAYOUT_TEXT_BYTES:
                            exceeded_limit.set()
                            process.kill()
                            return

                reader = Thread(target=drain_stdout, daemon=True)
                reader.start()
                try:
                    return_code = process.wait(timeout=EXTRACTION_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.wait()
                    reader.join(timeout=2)
                    process.stdout.close()
                    raise PDFSourceError(
                        "Isolated Poppler exceeded the 20-second extraction limit"
                    ) from exc
                reader.join(timeout=2)
                if reader.is_alive():
                    process.kill()
                    process.wait()
                    raise PDFSourceError("Isolated Poppler output stream did not close")
                if exceeded_limit.is_set():
                    raise PDFSourceError("Isolated Poppler output exceeds the 2 MiB limit")
                if return_code == 1:
                    raise PDFSourceError("Isolated Poppler could not extract this PDF")
                if return_code != 0:
                    # Only Poppler's documented input-open rejection is a
                    # source-specific negative fixture outcome. Docker reserved
                    # exits, signals/OOM, output errors and general errors must
                    # not masquerade as successful malformed-input coverage.
                    raise PDFSourceError(f"Isolated Poppler failed with unclassified exit code {return_code}")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if process.stdout is not None:
                    process.stdout.close()
                if reader is not None and reader.is_alive():
                    reader.join(timeout=2)
                _remove_sandbox_container(docker_prefix, docker_env, container_id_file)

        try:
            text = bytes(output).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PDFSourceError("Isolated Poppler did not return UTF-8 text") from exc
        if not text.strip():
            raise PDFSourceError("PDF has no extractable text; OCR is not supported")
        return text


def _line_records(page_text: str) -> list[tuple[str, int, int]]:
    records: list[tuple[str, int, int]] = []
    offset = 0
    for line_number, raw_line in enumerate(page_text.splitlines(keepends=True), start=1):
        line = raw_line.rstrip("\r\n")
        records.append((line, line_number, offset))
        offset += len(raw_line)
    return records


def _note_evidence(
    records: list[tuple[str, int, int]], page: int, pattern: re.Pattern[str]
) -> dict[str, Any] | None:
    joined_lines: list[str] = []
    starts: list[int] = []
    cursor = 0
    for line, _line_number, _offset in records:
        if joined_lines:
            cursor += 1
        starts.append(cursor)
        joined_lines.append(line)
        cursor += len(line)
    match = pattern.search(" ".join(joined_lines))
    if match is None:
        return None

    overlapping = [
        index for index, line in enumerate(joined_lines)
        if starts[index] < match.end()
        and starts[index] + len(line) > match.start()
    ]
    if not overlapping:
        return None
    first_index, last_index = overlapping[0], overlapping[-1]
    _first_line, first_number, first_offset = records[first_index]
    last_line, last_number, last_offset = records[last_index]
    quote = " | ".join(line.strip() for line in joined_lines[first_index:last_index + 1])
    return {
        "page": page,
        "line_start": first_number,
        "line_end": last_number,
        "quote": quote[:MAX_EVIDENCE_TEXT],
        "quote_truncated": len(quote) > MAX_EVIDENCE_TEXT,
        "page_text_char_start": first_offset,
        "page_text_char_end": last_offset + len(last_line),
        "matched_text": match.group(0)[:MAX_EVIDENCE_TEXT],
    }


def _denominator_values(text: str) -> set[int]:
    return {int(match.group(1)) for match in _DENOMINATOR_RE.finditer(text)}


def _try_arithmetic(count: int, denominator: int, reported: str) -> dict[str, Any] | None:
    precision = len(reported.partition(".")[2])
    try:
        return percentage_recalculation(count, denominator, reported, precision)
    except ValueError:
        return None


def parse_pdf_layout_text(layout_text: str, source_sha256: str) -> dict[str, Any]:
    """Find table-local count/percentage candidates in pdftotext layout text.

    PDF offsets are page-local character offsets in the recorded extracted
    layout stream, not byte offsets in the original PDF.
    """
    if not isinstance(layout_text, str) or not layout_text:
        raise PDFSourceError("Extracted layout text is empty")
    if not _SOURCE_HASH_RE.fullmatch(source_sha256):
        raise PDFSourceError("A lowercase SHA-256 for the original PDF is required")
    layout_bytes = layout_text.encode("utf-8")
    if len(layout_bytes) > MAX_LAYOUT_TEXT_BYTES:
        raise PDFSourceError("Extracted layout text exceeds the 2 MiB limit")
    layout_text_sha256 = hashlib.sha256(layout_bytes).hexdigest()

    pages = layout_text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if len(pages) > MAX_PDF_PAGES:
        raise PDFSourceError("PDF exceeds the 100-page limit")

    results: list[dict[str, Any]] = []
    tables_inspected = 0
    for page_number, page_text in enumerate(pages, start=1):
        records = _line_records(page_text)
        title_indexes = [
            index for index, (line, _line_number, _offset) in enumerate(records)
            if _TABLE_TITLE_RE.search(line)
        ]
        for title_position, title_index in enumerate(title_indexes):
            if tables_inspected >= MAX_TABLES:
                raise PDFSourceError("PDF exceeds the 200-table limit")
            section_end = (
                title_indexes[title_position + 1]
                if title_position + 1 < len(title_indexes) else len(records)
            )
            title_line = records[title_index][0].strip()
            header_scan_end = min(section_end, title_index + 9)
            header_indexes = []
            for index in range(title_index + 1, header_scan_end):
                line = records[index][0]
                if _COUNT_PERCENT_LINE_RE.fullmatch(line):
                    break
                if _HEADER_CUE_RE.search(line) or _DENOMINATOR_RE.search(line):
                    header_indexes.append(index)
            if not header_indexes:
                continue
            header_end = max(header_indexes)
            header_records = records[title_index + 1:header_end + 1]
            header_text = " ".join(line for line, _number, _offset in header_records)
            if not _HEADER_CUE_RE.search(header_text):
                continue
            tables_inspected += 1

            header_denominator_evidence = [
                {
                    "page": page_number,
                    "line": line_number,
                    "quote": line.strip()[:MAX_EVIDENCE_TEXT],
                    "page_text_char_start": offset,
                    "page_text_char_end": offset + len(line),
                }
                for line, line_number, offset in header_records
                if _DENOMINATOR_RE.search(line)
            ]
            denominator_values = _denominator_values(header_text)
            row_specific_denominator = bool(_ROW_SPECIFIC_RATIO_RE.search(header_text))

            data_records: list[dict[str, Any]] = []
            for line, line_number, offset in records[header_end + 1:section_end]:
                if _TABLE_END_RE.match(line):
                    break
                match = _COUNT_PERCENT_LINE_RE.fullmatch(line)
                if not match:
                    continue
                quote = line.strip()
                data_records.append({
                    "label": match.group("label").strip(),
                    "count": int(match.group("count")),
                    "reported": match.group("percent"),
                    "has_percent_symbol": bool(match.group("symbol")),
                    "page": page_number,
                    "line": line_number,
                    "page_text_char_start": offset,
                    "page_text_char_end": offset + len(line),
                    "quote": quote[:MAX_EVIDENCE_TEXT],
                    "quote_truncated": len(quote) > MAX_EVIDENCE_TEXT,
                })
                if len(data_records) > MAX_RESULTS:
                    raise PDFSourceError("PDF exceeds the per-table row-candidate limit")

            if not data_records:
                continue
            if len(results) + len(data_records) > MAX_RESULTS:
                raise PDFSourceError("PDF exceeds the 1,000-result limit")

            explicit_percent_context = bool(
                _EXPLICIT_PERCENT_RE.search(header_text)
                or any(row["has_percent_symbol"] for row in data_records)
            )
            denominator = next(iter(denominator_values)) if len(denominator_values) == 1 else None
            arithmetic_by_row = [
                _try_arithmetic(row["count"], denominator, row["reported"])
                if denominator is not None else None
                for row in data_records
            ]
            matching_rows = [
                (row, arithmetic)
                for row, arithmetic in zip(data_records, arithmetic_by_row)
                if arithmetic is not None and arithmetic["arithmetic_matches"]
            ]
            inferred_percent_context = (
                not explicit_percent_context
                and len(matching_rows) >= 2
                and len(matching_rows) * 2 >= len(data_records)
            )
            context_confirmed = explicit_percent_context or inferred_percent_context
            context_basis = (
                "explicit_percent_header_or_symbol" if explicit_percent_context
                else "repeated_count_denominator_matches" if inferred_percent_context
                else None
            )
            corroborating_rows = [
                {
                    "page": row["page"],
                    "line": row["line"],
                    "quote": row["quote"],
                }
                for row, _arithmetic in matching_rows[:8]
            ]

            table_records = records[title_index:section_end]
            rounding_note = _note_evidence(table_records, page_number, _ROUNDING_NOTE_RE)
            adjustment_note = _note_evidence(table_records, page_number, _ADJUSTMENT_NOTE_RE)

            for row, arithmetic in zip(data_records, arithmetic_by_row):
                reason: str | None = None
                status = "scope_ambiguous"
                row_denominator: int | None = denominator
                if len(denominator_values) > 1:
                    reason = "conflicting_table_header_denominators"
                    row_denominator = None
                elif denominator is None:
                    reason = "no_explicit_table_header_denominator"
                elif denominator <= 0:
                    reason = "nonpositive_table_header_denominator"
                    row_denominator = None
                elif row_specific_denominator:
                    reason = "row_specific_denominator_not_mapped"
                    row_denominator = None
                elif adjustment_note:
                    reason = "adjustment_method_scope_not_mapped"
                    row_denominator = None
                elif not context_confirmed:
                    reason = "percentage_context_not_explicit_or_corroborated"
                elif rounding_note:
                    status = "rounding_ambiguous"
                    reason = "source_rounding_convention_not_modeled"
                elif arithmetic is None:
                    reason = "invalid_or_unsupported_count_ratio"
                else:
                    status = (
                        "arithmetic_match" if arithmetic["arithmetic_matches"]
                        else "arithmetic_mismatch_candidate"
                    )

                evidence = {
                    "source_pdf_sha256": source_sha256,
                    "layout_text_sha256": layout_text_sha256,
                    "extractor": "pdftotext -layout -enc UTF-8",
                    "table_title": title_line[:MAX_EVIDENCE_TEXT],
                    "table_header_denominator_sources": header_denominator_evidence,
                    "row_label": row["label"][:MAX_EVIDENCE_TEXT],
                    "row_quote": row["quote"],
                    "row_quote_truncated": row["quote_truncated"],
                    "page": row["page"],
                    "line": row["line"],
                    "page_text_char_start": row["page_text_char_start"],
                    "page_text_char_end": row["page_text_char_end"],
                    "offset_note": "Offsets are character positions in the extracted page layout text, not byte offsets in the PDF.",
                    "percentage_context_basis": context_basis,
                    "context_corroborating_rows": corroborating_rows,
                }
                if rounding_note:
                    evidence["rounding_note"] = rounding_note
                if adjustment_note:
                    evidence["adjustment_note"] = adjustment_note
                result: dict[str, Any] = {
                    "status": status,
                    "reason": reason,
                    "numerator": row["count"],
                    "denominator": row_denominator,
                    "denominator_scope": "table_header" if row_denominator is not None else None,
                    "reported_percent": row["reported"],
                    "contract_expected_percent": (
                        arithmetic["rounded_percent"] if arithmetic is not None else None
                    ),
                    "exact_ratio_percent": (
                        arithmetic["exact_ratio_percent"] if arithmetic is not None else None
                    ),
                    "display_precision": len(row["reported"].partition(".")[2]),
                    "evidence": evidence,
                }
                results.append(result)

    return {
        "source_format": "PDF text layer",
        "source_sha256": source_sha256,
        "extractor": "pdftotext -layout -enc UTF-8",
        "layout_text_sha256": layout_text_sha256,
        "tables_inspected": tables_inspected,
        "percentage_cells_reviewed": len(results),
        "results": results,
        "limitations": [
            "PDF table identification uses layout-text heuristics; all candidates require human review.",
            "The extracted text hash and page-local character spans support replay but do not authenticate source origin.",
            "Only text-based PDFs are supported; image-only pages and OCR are not supported.",
            "A mismatch candidate is not proof of scientific error or correction eligibility.",
        ],
    }


def audit_pdf_percentage_tables(data: bytes) -> dict[str, Any]:
    """Extract and audit a bounded, local PDF without network access."""
    if not isinstance(data, bytes) or not data.startswith(_PDF_SIGNATURE):
        raise PDFSourceError("Input is not a PDF byte stream")
    if len(data) > MAX_PDF_BYTES:
        raise PDFSourceError("PDF exceeds the 8 MiB source limit")
    source_sha256 = hashlib.sha256(data).hexdigest()
    layout_text = _extract_layout_text(data)
    return parse_pdf_layout_text(layout_text, source_sha256)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="one local text-based PDF file")
    args = parser.parse_args(argv)
    try:
        data = read_regular(Path(args.pdf), MAX_PDF_BYTES)
        report = audit_pdf_percentage_tables(data)
    except (OSError, ValueError) as exc:
        print(f"PDF audit failed: {exc}", file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI invocation
    raise SystemExit(main())
