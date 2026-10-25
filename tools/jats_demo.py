"""Create and execute an entirely synthetic registered JATS demonstration.

Labels come from the explicit construction: 4/50 is 8.00%, 8.10% is a mismatch,
and a missing denominator stays unresolved. These closely related invented
fixtures are not independent scientific papers or an accuracy benchmark.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import sys

from tools import registered_jats_run as runner
from tools import verification_benchmark as vb
from tools.jats_source_adapter import canonical_bytes, component_id, interpretation_sha256


def prepare_demo(root: Path) -> tuple[dict, dict, dict]:
    root.mkdir(mode=0o700, exist_ok=False)
    inputs = root / 'inputs'
    inputs.mkdir()
    works, paths = [], {}
    for name, reported, label, denominator in (
        ('known-mismatch', '8.10', 'positive', True),
        ('known-match', '8.00', 'negative', True),
        ('scope-unknown', '8.10', 'unresolved', False),
    ):
        heading = 'n (%) N=50' if denominator else 'n (%)'
        text = f'4 ({reported}%)'
        element = f'<td>{text}</td>'.encode('ascii')
        data = (f'<article><body><table-wrap id="T1"><table><thead><tr>'
                f'<th>Outcome</th><th>{heading}</th></tr></thead><tbody><tr>'
                f'<td>Response</td>{element.decode("ascii")}</tr></tbody>'
                '</table></table-wrap></body></article>\n').encode('ascii')
        (inputs / f'{name}.xml').write_bytes(data)
        digest = sha256(data).hexdigest()
        start = data.index(element)
        target = component_id(digest, start, start + len(element), 0, len(text)) if label == 'positive' else None
        works.append({'work_id': name, 'family_id': name, 'source_sha256': digest,
                      'interpretation_sha256': interpretation_sha256(), 'label': label,
                      'eligible': True, 'exclusion_reason': None, 'target_id': target})
        paths[name] = f'{name}.xml'
    registry = {'schema_version': vb.REGISTRY_VERSION, 'exposure': 'synthetic',
                'label_basis': 'synthetic_construction', 'works': works}
    _files, identity = runner.capture_implementation()
    protocol = {'schema_version': vb.PROTOCOL_VERSION, 'registry_sha256': vb.commitment(registry),
                'implementation_sha256': vb.commitment(identity), 'schedule': list(paths),
                'max_elapsed_ms': 10_000, 'max_calls': 0, 'max_cost_micro_eur': 0}
    sources = {'schema_version': 'rw-jats-sources.v1', 'paths': paths}
    for name, value in (('registry', registry), ('protocol', protocol), ('sources', sources)):
        runner._write(root / f'{name}.json', value)
    runner._write(root / 'pins.json', {'registry_sha256': vb.commitment(registry),
                                      'protocol_sha256': vb.commitment(protocol)})
    return registry, protocol, sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        registry, protocol, sources = prepare_demo(args.output_dir)
        summary = runner.run_registered(
            registry, protocol, sources, args.output_dir / 'inputs', args.output_dir / 'run',
            expected_registry_sha256=vb.commitment(registry),
            expected_protocol_sha256=vb.commitment(protocol),
        )
        sys.stdout.buffer.write(canonical_bytes(summary))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        sys.stderr.buffer.write(b'{"status":"invalid","code":"SYNTHETIC_JATS_DEMO_FAILED"}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
