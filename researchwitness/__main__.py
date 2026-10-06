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
from .paper_audit import capabilities as paper_screen_capabilities, run_paper_audit
from .resolution import project
from .review import REVIEW_AREAS, html_review_report, scaffold_review, validate_review_file
from .scaffold import scaffold as scaffold_intake
from .statistics import capabilities as summary_capabilities, validate_summary_file
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
        description='Screen paper text for limited candidate anomalies, record reviews, and replay bounded claim checks.',
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

    command = sub.add_parser('review-scaffold')
    command.add_argument('--source-file', type=Path, required=True,
                         help='UTF-8 paper text capture to copy into the review workspace')
    command.add_argument('--identifier', required=True, help='DOI, arXiv identifier, or local source identifier')
    command.add_argument('--source-version', required=True, help='Exact version represented by the text capture')
    command.add_argument('--reviewed-on', type=date.fromisoformat, default=date.today())
    command.add_argument('--output', type=Path, required=True, help='New review workspace directory')

    command = sub.add_parser('validate-review')
    command.add_argument('review', type=Path)
    command.add_argument('--html', type=Path, default=None)

    command = sub.add_parser('check-summary')
    command.add_argument('input', type=Path,
                         help='Summary-check JSON with its declared UTF-8 source text beside it')

    command = sub.add_parser('paper-audit')
    command.add_argument('input', type=Path, help='UTF-8 .txt/.md or a born-digital .pdf paper capture')
    command.add_argument('--output', type=Path, required=True, help='New directory for source copy and screening reports')
    command.add_argument('--identifier', default=None, help='DOI, arXiv identifier, or local source identifier')
    command.add_argument('--source-version', default=None, help='Exact version represented by the paper capture')

    command = sub.add_parser('schema')
    command.add_argument('name', choices=('case', 'intake', 'review', 'summary-check', 'paper-audit'))

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
            print(json.dumps({'version': VERSION, 'checkers': capabilities(),
                              'empirical_checks': summary_capabilities(),
                              'paper_screens': paper_screen_capabilities()}, indent=2))
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
        if args.command == 'review-scaffold':
            root = scaffold_review(args.source_file, args.output, args.identifier,
                                   args.source_version, args.reviewed_on)
            print(json.dumps({'review_scaffold': str(root),
                              'review_areas': len(REVIEW_AREAS),
                              'source_capture_status': 'unverified'}, indent=2))
            return 0
        if args.command == 'validate-review':
            report = validate_review_file(args.review)
            if args.html is not None:
                args.html.write_text(html_review_report(report), encoding='utf-8')
                report['html_report'] = str(args.html)
            print(json.dumps(report, indent=2, ensure_ascii=True))
            return 0
        if args.command == 'check-summary':
            print(json.dumps(validate_summary_file(args.input), indent=2, ensure_ascii=True))
            return 0
        if args.command == 'paper-audit':
            report = run_paper_audit(args.input, args.output, args.identifier, args.source_version)
            print(json.dumps(report, indent=2, ensure_ascii=True))
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
