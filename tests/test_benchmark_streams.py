"""Canonical CLI bytes must not depend on platform text newline translation."""
import io
import json
from pathlib import Path
import sys

import pytest

from tools import verification_benchmark as vb

FIXTURE = Path(__file__).resolve().parents[1] / 'examples' / 'verification-benchmark'


@pytest.mark.parametrize('invalid', [False, True])
def test_canonical_stream_bytes_ignore_crlf_translation(monkeypatch, invalid):
    pins = json.loads((FIXTURE / 'pins.json').read_text(encoding='utf-8'))
    args = ['--registry', str(FIXTURE / 'registry.json'),
            '--protocol', str(FIXTURE / 'protocol.json'),
            '--run', str(FIXTURE / 'run.json'),
            '--expected-registry-sha256',
            '0' * 64 if invalid else pins['expected_registry_sha256'],
            '--expected-protocol-sha256', pins['expected_protocol_sha256']]
    out_buffer, err_buffer = io.BytesIO(), io.BytesIO()
    out = io.TextIOWrapper(out_buffer, encoding='ascii', newline='\r\n')
    err = io.TextIOWrapper(err_buffer, encoding='ascii', newline='\r\n')
    with monkeypatch.context() as scoped:
        scoped.setattr(sys, 'stdout', out)
        scoped.setattr(sys, 'stderr', err)
        result = vb.main(args)
        out.flush()
        err.flush()
        stdout, stderr = out_buffer.getvalue(), err_buffer.getvalue()
    assert result == (2 if invalid else 0)
    payload = stderr if invalid else stdout
    assert (stdout if invalid else stderr) == b''
    assert payload == vb.canonical_bytes(json.loads(payload))
    assert payload.endswith(b'\n') and b'\r' not in payload
