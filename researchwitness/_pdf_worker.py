"""Bounded pypdf extraction worker for the untrusted paper-ingestion front end.

The parent starts this file in a separate interpreter with a wall-clock timeout.
On POSIX, this worker also applies address-space and CPU limits before importing
pypdf. It is process isolation, not a full operating-system sandbox.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import sys


MAX_SOURCE_BYTES = 32 * 1024 * 1024


class WorkerLimit(Exception):
    pass


def _limits(memory_bytes: int, cpu_seconds: int) -> None:
    try:
        import resource
    except ImportError:
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except (OSError, ValueError):
        # The parent timeout and source/output bounds still apply where rlimits
        # are unavailable or rejected by the host.
        return


def _result(
    status: str,
    extractor: str,
    page_records: list[dict],
    warnings: list[str],
    output: bytes = b'',
) -> None:
    payload = {
        'status': status,
        'extractor': extractor,
        'page_records': page_records,
        'warnings': warnings,
        'text_base64': base64.b64encode(output).decode('ascii'),
    }
    sys.stdout.write(json.dumps(payload, separators=(',', ':'), ensure_ascii=True))


def main(argv: list[str]) -> int:
    if len(argv) != 7:
        _result('WORKER_PROTOCOL_ERROR', 'pypdf isolated worker', [], ['Invalid worker arguments.'])
        return 0
    source_path = Path(argv[1])
    max_pages, max_page_bytes, max_text_bytes, memory_bytes, cpu_seconds = map(int, argv[2:])
    _limits(memory_bytes, cpu_seconds)
    try:
        import pypdf
        from pypdf import PdfReader
    except ImportError:
        _result('PARSER_UNAVAILABLE', 'pypdf (optional paper extra)', [], [
            'Install researchwitness[paper] to extract PDF text. No OCR was attempted.'
        ])
        return 0

    extractor = f'pypdf {pypdf.__version__} (separate worker; {cpu_seconds}s CPU and '
    extractor += f'{memory_bytes // (1024 * 1024)} MiB address-space limits where supported)'
    try:
        if source_path.stat().st_size > MAX_SOURCE_BYTES:
            raise WorkerLimit('PDF source-size limit exceeded')
        source_bytes = source_path.read_bytes()
        if len(source_bytes) > MAX_SOURCE_BYTES:
            raise WorkerLimit('PDF source-size limit exceeded')
        reader = PdfReader(BytesIO(source_bytes), strict=True)
        if reader.is_encrypted:
            raise WorkerLimit('Encrypted PDFs are not supported')
        page_count = len(reader.pages)
        if not 1 <= page_count <= max_pages:
            raise WorkerLimit('PDF page-count limit exceeded')
        page_texts: list[bytes] = []
        page_records: list[dict] = []
        total = 0
        for page_number, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ''
            if type(extracted) is not str:
                raise WorkerLimit('PDF parser returned non-text page content')
            page_bytes = extracted.encode('utf-8')
            if len(page_bytes) > max_page_bytes:
                raise WorkerLimit('PDF page extracted-text limit exceeded')
            total += len(page_bytes)
            if total > max_text_bytes:
                raise WorkerLimit('PDF total extracted-text limit exceeded')
            page_texts.append(page_bytes)
            page_records.append({
                'page_number': page_number,
                'character_count': len(extracted),
                'status': 'TEXT_EXTRACTED' if extracted.strip() else 'NO_EXTRACTABLE_TEXT',
            })

        separator = b'\n\f\n'
        chunks: list[bytes] = []
        offset = 0
        for index, page_bytes in enumerate(page_texts):
            record = page_records[index]
            record['text_start_byte'] = offset
            record['text_end_byte'] = offset + len(page_bytes)
            chunks.append(page_bytes)
            offset += len(page_bytes)
            if index + 1 < len(page_texts):
                chunks.append(separator)
                offset += len(separator)
        if offset > max_text_bytes:
            raise WorkerLimit('PDF total extracted-text limit exceeded')
        output = b''.join(chunks)
        empty_pages = [record['page_number'] for record in page_records
                       if record['status'] == 'NO_EXTRACTABLE_TEXT']
        if len(empty_pages) == page_count:
            status = 'NO_EXTRACTABLE_TEXT'
            warnings = [
                'No text was extracted. Pages may be image-only or use unsupported encodings; no OCR was attempted.'
            ]
        elif empty_pages:
            status = 'PARTIAL_TEXT'
            warnings = ['No extractable text on physical PDF pages: ' + ', '.join(map(str, empty_pages))]
        else:
            status = 'TEXT_AVAILABLE'
            warnings = []
        _result(status, extractor, page_records, warnings, output)
    except WorkerLimit as exc:
        _result('LIMIT_OR_UNSUPPORTED', extractor, [], [
            'PDF extraction stopped at a configured limit or unsupported document feature (' + str(exc) + '). '
            'No detector was run.'
        ])
    except BaseException as exc:
        # Keep exception values and parser diagnostics out of the report because
        # malformed documents may place attacker-controlled text in messages.
        _result('MALFORMED_OR_UNSUPPORTED', extractor, [], [
            'PDF extraction failed (' + type(exc).__name__ + '). No OCR or repair was attempted.'
        ])
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
