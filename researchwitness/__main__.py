"""CLI with explicit exit codes and no network or communication side effects."""
from __future__ import annotations

import argparse
from datetime import date
from importlib.resources import files as package_files
import json
from pathlib import Path
import sys
import zipfile

from .capsule import VERSION, evaluate_loaded, load_bundle, subject_digest
from .checkers import KINDS, capabilities
from .intake import prepare, validate_intake_file
from .product import contact_draft, contact_readiness, html_report
from .resolution import project
from .scaffold import scaffold as scaffold_intake
from .strict import Invalid, canonical


def _write_deterministic_zip(path: Path, entries: dict[str, bytes]) -> None:
    with path.open('xb') as output:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, content in sorted(entries.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100600 << 16
                archive.writestr(info, content)


def _evaluate(bundle: Path, as_of: date, pin: str | None = None):
    case, data = load_bundle(bundle)
    report = evaluate_loaded(case, data, as_of, pin)
    return case, data, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='researchwitness',
        description='Build and verify reproducible evidence for explicit scientific claims.',
    )
    parser.add_argument('--version', action='version', version='%(prog)s ' + VERSION)
    sub = parser.add_subparsers(dest='command', required=True)

    for name in ('verify', 'subject', 'pack', 'report', 'contact-draft'):
        command = sub.add_parser(name)
        command.add_argument('bundle', type=Path)
        command.add_argument('--as-of', type=date.fromisoformat, default=date.today())
        if name not in ('subject',):
            command.add_argument('--expected-bundle-sha256', default=None)
        if name == 'pack':
            command.add_argument('--output', type=Path, required=True)
        if name in ('report', 'contact-draft'):
            command.add_argument('--output', type=Path, required=True)

    command = sub.add_parser('prepare')
    command.add_argument('intake', type=Path)
    command.add_argument('--output', type=Path, required=True)

    command = sub.add_parser('validate-intake')
    command.add_argument('intake', type=Path)

    command = sub.add_parser('scaffold')
    command.add_argument('kind', choices=sorted(KINDS))
    command.add_argument('--output', type=Path, required=True, help='New directory for the synthetic intake scaffold')

    command = sub.add_parser('schema')
    command.add_argument('name', choices=('case', 'intake'))

    command = sub.add_parser('audit')
    command.add_argument('intake', type=Path)
    command.add_argument('--output', type=Path, required=True, help='New evidence-bundle directory')
    command.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    command.add_argument('--html', type=Path, default=None)

    command = sub.add_parser('capabilities')
    command.add_argument('--json', action='store_true',
                         help='Emit the machine-readable capability registry (the default format).')

    command = sub.add_parser('timeline')
    command.add_argument('bundle', type=Path)
    command.add_argument('--timeline', type=Path, required=True)
    command.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    command.add_argument('--expected-timeline-sha256', default=None)

    args = parser.parse_args(argv)
    try:
        if args.command == 'capabilities':
            print(json.dumps({'version': VERSION, 'checkers': capabilities()}, indent=2))
            return 0
        if args.command == 'validate-intake':
            print(json.dumps(validate_intake_file(args.intake), indent=2))
            return 0
        if args.command == 'scaffold':
            root = scaffold_intake(args.kind, args.output)
            print(json.dumps({'scaffold': str(root), 'kind': args.kind,
                              'source_capture_status': 'synthetic',
                              'correction_status': 'unchecked'}, indent=2))
            return 0
        if args.command == 'schema':
            schema = package_files('researchwitness').joinpath('schemas', f'{args.name}.schema.json')
            print(schema.read_text(encoding='utf-8'), end='')
            return 0
        if args.command == 'prepare':
            root = prepare(args.intake, args.output)
            print(json.dumps({'prepared': str(root)}, indent=2))
            return 0
        if args.command == 'audit':
            root = prepare(args.intake, args.output)
            case, data, report = _evaluate(root, args.as_of)
            readiness = contact_readiness(report)
            output = {'bundle': str(root), 'report': report, 'contact_readiness': readiness}
            if args.html is not None:
                args.html.write_text(html_report(report, readiness), encoding='utf-8')
                output['html_report'] = str(args.html)
            print(json.dumps(output, indent=2, ensure_ascii=True))
            return 0

        case, data = load_bundle(args.bundle)
        if args.command == 'timeline':
            from .strict import Bundle, loads
            path = args.timeline.absolute()
            timeline = loads(Bundle(path.parent).read(path.name, 2 * 1024 * 1024))
            print(json.dumps(project(case, data, timeline, args.as_of, args.expected_timeline_sha256), indent=2))
            return 0

        if args.command == 'subject':
            print(subject_digest(case))
            return 0

        report = evaluate_loaded(case, data, args.as_of, args.expected_bundle_sha256)
        readiness = contact_readiness(report)
        if args.command == 'pack':
            entries = dict(data)
            entries['case.json'] = canonical(case) + b'\n'
            entries['report.json'] = canonical(report) + b'\n'
            entries['contact-readiness.json'] = canonical(readiness) + b'\n'
            _write_deterministic_zip(args.output, entries)
            print(json.dumps({'exported': str(args.output), 'decision': report['decision'],
                              'contact_readiness': readiness['status'], 'disclosure': 'private'}, indent=2))
            return 0
        if args.command == 'report':
            args.output.write_text(html_report(report, readiness), encoding='utf-8')
            print(json.dumps({'report': str(args.output), 'decision': report['decision'],
                              'contact_readiness': readiness['status']}, indent=2))
            return 0
        if args.command == 'contact-draft':
            try:
                draft = contact_draft(case, report, readiness)
            except ValueError as exc:
                raise Invalid(str(exc)) from exc
            args.output.write_text(draft, encoding='utf-8')
            print(json.dumps({'draft': str(args.output), 'status': 'USER_REVIEW_REQUIRED'}, indent=2))
            return 0

        result = dict(report)
        result['contact_readiness'] = readiness
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (Invalid, OSError) as exc:
        print(json.dumps({'decision': 'INVALID', 'error': str(exc),
                          'external_actions': 'OUT_OF_SCOPE'}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
