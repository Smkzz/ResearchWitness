"""Fixed offline JATS worker. No caller-selected commands, modules or providers."""
from __future__ import annotations

import sys

from tools.jats_source_adapter import SourceAdapterError, audit_jats_source, bounded_report_bytes

MAX_SOURCE_BYTES = 8 * 1024 * 1024


def main() -> int:
    try:
        source = sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1)
        if not source or len(source) > MAX_SOURCE_BYTES:
            raise SourceAdapterError('SOURCE_BYTE_LIMIT')
        result = bounded_report_bytes(audit_jats_source(source))
    except (ValueError, TypeError, KeyError, RecursionError):
        # Never echo a local path, source text or raw third-party exception.
        sys.stderr.buffer.write(b'{"code":"JATS_WORKER_REJECTED","status":"invalid"}\n')
        return 2
    sys.stdout.buffer.write(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
