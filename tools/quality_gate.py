"""Offline release qualification for maintainers.

Requires development dependencies already installed. It performs no network fetches.
"""
from __future__ import annotations

import ast
import compileall
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'researchwitness'
BANNED_IMPORT_ROOTS = {'socket', 'urllib', 'http', 'requests', 'subprocess', 'pickle', 'ctypes'}
BANNED_CALLS = {'eval', 'exec', 'compile', '__import__'}


def run(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True, env=env)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_core() -> None:
    for path in sorted(CORE.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split('.')[0] for alias in node.names}
                banned = roots & BANNED_IMPORT_ROOTS
                if path.name == 'paper_audit.py':
                    banned -= {'subprocess'}
                if banned:
                    raise RuntimeError(f'banned import in trusted core: {path.name}: {banned}')
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split('.')[0]
                if root in BANNED_IMPORT_ROOTS and not (path.name == 'paper_audit.py' and root == 'subprocess'):
                    raise RuntimeError(f'banned import in trusted core: {path.name}: {root}')
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                raise RuntimeError(f'banned dynamic call in trusted core: {path.name}: {node.func.id}')

    audit_path = CORE / 'paper_audit.py'
    audit_tree = ast.parse(audit_path.read_text(encoding='utf-8'), filename=str(audit_path))
    process_calls = [
        node for node in ast.walk(audit_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == 'subprocess'
    ]
    if len(process_calls) != 1 or process_calls[0].func.attr != 'run':
        raise RuntimeError('paper PDF extraction must use exactly one subprocess.run call')
    process_call = process_calls[0]
    keywords = {item.arg: item.value for item in process_call.keywords}
    if (not isinstance(process_call.args[0], ast.Name) or process_call.args[0].id != 'command'
            or not isinstance(keywords.get('shell'), ast.Constant) or keywords['shell'].value is not False
            or not isinstance(keywords.get('check'), ast.Constant) or keywords['check'].value is not False
            or not isinstance(keywords.get('timeout'), ast.Name)
            or keywords['timeout'].id != 'MAX_PDF_EXTRACTION_SECONDS'):
        raise RuntimeError('paper PDF worker process call is missing its fixed argv, shell, or timeout constraints')
    worker_path = CORE / '_pdf_worker.py'
    worker_tree = ast.parse(worker_path.read_text(encoding='utf-8'), filename=str(worker_path))
    worker_imports = set()
    for node in ast.walk(worker_tree):
        if isinstance(node, ast.Import):
            worker_imports.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            worker_imports.add(node.module.split('.')[0])
    if worker_imports & (BANNED_IMPORT_ROOTS - {'subprocess'}):
        raise RuntimeError('PDF worker imports a prohibited network, dynamic-code, or deserialization module')
    if 'subprocess' in worker_imports:
        raise RuntimeError('PDF worker must not start another process')
    worker_calls = [
        node for node in ast.walk(worker_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in BANNED_CALLS
    ]
    if worker_calls:
        raise RuntimeError('PDF worker contains a banned dynamic-code call')

    main_function = next(
        (node for node in worker_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main'),
        None,
    )
    if main_function is None:
        raise RuntimeError('PDF worker is missing its bounded main entry point')
    limit_calls = [
        node for node in ast.walk(main_function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_limits'
    ]
    pypdf_imports = [
        node for node in ast.walk(main_function)
        if (isinstance(node, ast.Import) and any(alias.name == 'pypdf' for alias in node.names))
        or (isinstance(node, ast.ImportFrom) and node.module == 'pypdf')
    ]
    if (len(limit_calls) != 1 or not pypdf_imports
            or limit_calls[0].lineno >= min(node.lineno for node in pypdf_imports)):
        raise RuntimeError('PDF resource limits must be applied before importing pypdf')
    setrlimit_calls = [
        node for node in ast.walk(worker_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'resource'
        and node.func.attr == 'setrlimit'
    ]
    limited_constants = {
        argument.attr
        for call in setrlimit_calls for argument in call.args[:1]
        if isinstance(argument, ast.Attribute) and isinstance(argument.value, ast.Name)
        and argument.value.id == 'resource'
    }
    if not {'RLIMIT_CPU', 'RLIMIT_AS'} <= limited_constants:
        raise RuntimeError('PDF worker must configure CPU and address-space resource limits')


def check_paper_audit_development_results() -> None:
    from jsonschema import Draft202012Validator
    from tools.run_paper_audit_wave import _matches

    validation = ROOT / 'validation/paper-audit-wave-1'
    manifest = json.loads((validation / 'cases.json').read_text(encoding='utf-8'))
    summary = json.loads((validation / 'results/summary.json').read_text(encoding='utf-8'))
    schema = json.loads((ROOT / 'schemas/paper-audit.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    case_results = []
    candidate_items = matched_items = unsupported = detected = 0
    negative_papers = negative_items = negative_scope_notes = scope_notes = 0
    extraction_errors = repeatable = arithmetic_candidates = 0

    expected_ids = {case['case_id'] for case in manifest['cases']}
    result_root = validation / 'results'
    actual_ids = {path.name for path in result_root.iterdir() if path.is_dir()}
    if actual_ids != expected_ids:
        raise RuntimeError('paper-audit development result folders do not match the pinned manifest')
    if summary.get('holdout', {}).get('status') != 'NOT_RUN':
        raise RuntimeError('development corpus must not claim a sealed holdout')

    for case in manifest['cases']:
        case_id = case['case_id']
        case_dir = result_root / case_id
        report = json.loads((case_dir / 'report.json').read_text(encoding='utf-8'))
        evaluation = json.loads((case_dir / 'evaluation.json').read_text(encoding='utf-8'))
        errors = list(validator.iter_errors(report))
        if errors:
            raise RuntimeError(f'{case_id}: archived paper-audit report fails schema validation')
        if (report['paper_error_established'] is not False or report['verified_findings']
                or evaluation['run']['verified_finding_count'] != 0):
            raise RuntimeError(f'{case_id}: archived candidate report crossed the verification boundary')
        candidates = report['candidate_anomalies']
        if (evaluation['case_id'] != case_id or evaluation['role'] != case['role']
                or evaluation['run']['candidate_count'] != len(candidates)
                or report['source']['sha256'] != evaluation['source']['rendered_markdown_sha256']):
            raise RuntimeError(f'{case_id}: archived evaluation does not match its report or manifest')
        if not evaluation['run']['deterministic_report_json'] or not evaluation['run']['deterministic_report_html']:
            raise RuntimeError(f'{case_id}: archived run did not establish JSON and HTML repeatability')

        candidate_items += len(candidates)
        arithmetic_candidates += sum(
            item['type'] in ('TABLE_PERCENTAGE_ARITHMETIC_MISMATCH',
                             'EXPLICIT_EXCLUSION_FLOW_ARITHMETIC_MISMATCH')
            for item in candidates
        )
        scope_notes += len(report['possible_scope_differences'])
        negative_scope_notes += int(case['role'] == 'development_negative'
                                    and bool(report['possible_scope_differences']))
        extraction_errors += int(report['extraction']['status'] != 'TEXT_AVAILABLE')
        repeatable += 1

        if case['role'] == 'development_positive':
            expected = case['expected']
            if expected['candidate_type'] is None:
                unsupported += 1
                if evaluation['outcome'] != 'UNSUPPORTED_EXPECTED' or candidates:
                    raise RuntimeError(f'{case_id}: unsupported positive outcome does not match the manifest')
            else:
                matches = [item for item in candidates if _matches(item, expected)]
                expected_count = (len(expected['target']['reported_percent'])
                                  if isinstance(expected['target'].get('reported_percent'), list) else 1)
                if len(matches) == expected_count:
                    detected += 1
                    outcome = 'DETECTED'
                elif matches:
                    outcome = 'PARTIALLY_DETECTED'
                else:
                    outcome = 'MISSED'
                if evaluation['outcome'] != outcome:
                    raise RuntimeError(f'{case_id}: archived positive evaluation no longer matches its report')
                matched_items += len(matches)
                if evaluation['matched_candidate_count'] != len(matches):
                    raise RuntimeError(f'{case_id}: archived matched candidate count is inconsistent')
            if expected['candidate_type'] is not None:
                unmatched = len(candidates) - len(matches)
                if unmatched < 0:
                    raise RuntimeError(f'{case_id}: positive candidate matching is inconsistent')
        else:
            if evaluation['outcome'] != ('FALSE_POSITIVE' if candidates else 'NO_CANDIDATE'):
                raise RuntimeError(f'{case_id}: negative-control evaluation does not match its report')
            if candidates:
                negative_papers += 1
                negative_items += len(candidates)

        case_results.append(evaluation)

    positives = sum(item['role'] == 'development_positive' for item in case_results)
    negatives = sum(item['role'] == 'development_negative' for item in case_results)
    unmatched_items = candidate_items - matched_items
    metrics = {
        'positive_cases': positives,
        'known_issue_rediscovery': detected,
        'known_issue_rediscovery_rate': detected / positives if positives else None,
        'unsupported_positive_cases': unsupported,
        'unsupported_positive_rate': unsupported / positives if positives else None,
        'supported_positive_cases': positives - unsupported,
        'candidate_items_with_recomputed_arithmetic': arithmetic_candidates,
        'reproducible_arithmetic_rate_for_candidate_items': arithmetic_candidates / candidate_items if candidate_items else None,
        'candidate_items': candidate_items,
        'matched_candidate_items': matched_items,
        'unmatched_candidate_items': unmatched_items,
        'candidate_precision_on_selected_development_set': matched_items / candidate_items if candidate_items else None,
        'negative_controls': negatives,
        'negative_control_papers_with_candidates': negative_papers,
        'false_positive_rate_on_selected_negative_controls': negative_papers / negatives if negatives else None,
        'false_positive_candidates_per_negative_paper': negative_items / negatives if negatives else None,
        'possible_scope_difference_notes': scope_notes,
        'negative_control_papers_with_scope_notes': negative_scope_notes,
        'scope_note_adjudication': 'NOT_SYSTEMATICALLY_SCORED',
        'real_source_extraction_errors': extraction_errors,
        'verified_findings_promoted': 0,
        'repeatable_papers': repeatable,
        'repeatability_rate': repeatable / len(case_results) if case_results else None,
    }
    if summary.get('metrics') != metrics:
        raise RuntimeError('paper-audit development summary metrics do not match archived per-case reports')


def check_source_checksums() -> None:
    from tools.make_release import included_files

    manifest = ROOT / 'CHECKSUMS.sha256'
    recorded = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        expected, relative = line.split('  ', 1)
        if relative in recorded:
            raise RuntimeError(f'duplicate source checksum entry: {relative}')
        recorded[relative] = expected
    files = {path.relative_to(ROOT).as_posix(): path
             for path in included_files(include_checksums=False)}
    if set(recorded) != set(files):
        raise RuntimeError('source checksum manifest does not match release-file selection')
    for relative, path in files.items():
        if sha256(path) != recorded[relative]:
            raise RuntimeError(f'source checksum mismatch: {relative}')


def main() -> int:
    pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    version = pyproject['project']['version']
    sys.path.insert(0, str(ROOT))
    from researchwitness import VERSION
    from tools.write_schema import (
        make as make_schema,
        make_intake_schema,
        make_paper_audit_schema,
        make_review_schema,
        make_summary_check_schema,
    )
    from tools.make_examples import build_capability_examples
    from tools.review_frozen_screen import run as review_frozen_screen
    from benchmarks.run_synthetic import run as run_synthetic

    if VERSION != version:
        raise RuntimeError(f'version mismatch: package={VERSION} pyproject={version}')
    check_source_checksums()
    if json.loads((ROOT / 'schemas/case.schema.json').read_text()) != make_schema():
        raise RuntimeError('generated schema drift')
    if json.loads((ROOT / 'schemas/intake.schema.json').read_text()) != make_intake_schema():
        raise RuntimeError('generated intake schema drift')
    if json.loads((ROOT / 'researchwitness/schemas/case.schema.json').read_text()) != make_schema():
        raise RuntimeError('packaged case schema drift')
    if json.loads((ROOT / 'researchwitness/schemas/intake.schema.json').read_text()) != make_intake_schema():
        raise RuntimeError('packaged intake schema drift')
    for schema_name, schema_factory in (
        ('review.schema.json', make_review_schema),
        ('summary-check.schema.json', make_summary_check_schema),
        ('paper-audit.schema.json', make_paper_audit_schema),
    ):
        expected = schema_factory()
        for directory in (ROOT / 'schemas', ROOT / 'researchwitness/schemas'):
            if json.loads((directory / schema_name).read_text()) != expected:
                raise RuntimeError(f'{directory.name}/{schema_name} drift')
    if json.loads((ROOT / 'researchwitness/capability_examples.json').read_text()) != build_capability_examples(ROOT / 'examples'):
        raise RuntimeError('packaged capability example drift')
    check_paper_audit_development_results()
    stored_screen_review = json.loads((ROOT / 'validation/verifier-wave/screening-15-review.json').read_text())
    fresh_screen_review = review_frozen_screen()
    for key in ('case_count_by_category', 'cases', 'execution', 'sealed_holdout'):
        if stored_screen_review[key] != fresh_screen_review[key]:
            raise RuntimeError(f'frozen-screen review drift: {key}')
    if not compileall.compile_dir(CORE, quiet=1):
        raise RuntimeError('compileall failed')
    scan_core()

    tests = run(sys.executable, '-m', 'pytest', '-q')

    with tempfile.TemporaryDirectory(prefix='researchwitness-quality-') as td:
        temp = Path(td)
        bench = run_synthetic(temp / 'evidence')
        if bench['matched'] != bench['case_count']:
            raise RuntimeError('synthetic conformance mismatch')
        real = json.loads(run(sys.executable, 'validation/mvp_real/run_validation.py').stdout)
        if real['matched'] != real['cases']:
            raise RuntimeError('MVP real-paper replay mismatch')

        build_env = dict(os.environ)
        build_env['SOURCE_DATE_EPOCH'] = '1760000000'
        dist = temp / 'dist-a'
        dist2 = temp / 'dist-b'
        dist.mkdir(); dist2.mkdir()
        run(sys.executable, '-m', 'pip', 'wheel', '.', '--no-deps', '--no-build-isolation', '-w', str(dist), env=build_env)
        run(sys.executable, '-m', 'pip', 'wheel', '.', '--no-deps', '--no-build-isolation', '-w', str(dist2), env=build_env)
        wheels = list(dist.glob('researchwitness-*.whl'))
        wheels2 = list(dist2.glob('researchwitness-*.whl'))
        if len(wheels) != 1 or len(wheels2) != 1:
            raise RuntimeError('expected exactly one wheel per build')
        wheel, wheel2 = wheels[0], wheels2[0]
        if wheel.read_bytes() != wheel2.read_bytes():
            raise RuntimeError('wheel build is not reproducible with SOURCE_DATE_EPOCH')
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            if any(name.endswith(('.pyc', '.pyo')) or '/tests/' in name for name in names):
                raise RuntimeError('wheel contains development artifacts')
            if not any(name == 'researchwitness/__main__.py' for name in names):
                raise RuntimeError('wheel missing CLI module')
            if 'researchwitness/capability_examples.json' not in names:
                raise RuntimeError('wheel missing capability example data')
            if 'researchwitness/schemas/intake.schema.json' not in names:
                raise RuntimeError('wheel missing agent-intake JSON Schema')
            if 'researchwitness/schemas/review.schema.json' not in names:
                raise RuntimeError('wheel missing review-ledger JSON Schema')
            if 'researchwitness/schemas/summary-check.schema.json' not in names:
                raise RuntimeError('wheel missing summary-check JSON Schema')
            if 'researchwitness/schemas/paper-audit.schema.json' not in names:
                raise RuntimeError('wheel missing paper-audit JSON Schema')
            if 'researchwitness/paper_audit.py' not in names:
                raise RuntimeError('wheel missing paper-audit command module')
            if 'researchwitness/_pdf_worker.py' not in names:
                raise RuntimeError('wheel missing isolated PDF extraction worker')

        env = temp / 'venv'
        venv.EnvBuilder(with_pip=True, clear=True).create(env)
        python = env / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        cli = env / ('Scripts/researchwitness.exe' if sys.platform == 'win32' else 'bin/researchwitness')
        run(str(python), '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel), cwd=temp)
        version_out = run(str(cli), '--version', cwd=temp).stdout.strip()
        if version_out != f'researchwitness {version}':
            raise RuntimeError('installed CLI version mismatch')
        smoke = json.loads(run(str(cli), 'verify', str(ROOT / 'examples/counterexample'),
                               '--as-of', '2026-10-04', cwd=temp).stdout)
        if smoke['decision'] != 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED':
            raise RuntimeError('installed-wheel smoke check failed')
        if smoke['paper_error_established'] or smoke['external_actions'] != 'OUT_OF_SCOPE':
            raise RuntimeError('scope invariant failed in installed wheel')
        capabilities = json.loads(run(str(cli), 'capabilities', '--json', cwd=temp).stdout)
        if len(capabilities['checkers']) != 10:
            raise RuntimeError('installed capability registry is incomplete')
        if (len(capabilities['paper_screens']) != 3
                or any(item['role'] != 'candidate_discovery_only'
                       for item in capabilities['paper_screens'])):
            raise RuntimeError('installed paper-screen capability registry is incomplete')
        schema = json.loads(run(str(cli), 'schema', 'intake', cwd=temp).stdout)
        if schema['title'] != 'ResearchWitness agent intake 0.1':
            raise RuntimeError('installed intake schema command failed')
        paper_schema = json.loads(run(str(cli), 'schema', 'paper-audit', cwd=temp).stdout)
        if paper_schema['title'] != 'ResearchWitness bounded paper-screening report 0.2':
            raise RuntimeError('installed paper-audit schema command failed')
        paper_result = json.loads(run(
            str(cli), 'paper-audit', str(ROOT / 'examples/paper-audit/paper.md'),
            '--identifier', 'synthetic:paper-audit', '--source-version', 'fixture-v1',
            '--output', str(temp / 'paper-audit'), cwd=temp,
        ).stdout)
        if (paper_result['decision'] != 'NO_CANDIDATES_IN_SUPPORTED_SCAN'
                or paper_result['paper_error_established']
                or paper_result['candidate_anomalies'] != 0
                or paper_result['possible_scope_differences'] < 1):
            raise RuntimeError('installed paper-audit smoke check failed')
        review_result = json.loads(run(
            str(cli), 'validate-review', str(ROOT / 'examples/paper-review-ledger/review.json'), cwd=temp,
        ).stdout)
        if (review_result['paper_error_established']
                or review_result['coverage']['areas_not_reviewed'] != 9
                or review_result['coverage']['all_areas_accounted_for'] is not False
                or review_result['findings'][0]['verification']['decision']
                != 'TABULAR_SUMMARY_MISMATCH_VERIFIED'):
            raise RuntimeError('installed review-ledger smoke check failed')
        summary_result = json.loads(run(
            str(cli), 'check-summary', str(ROOT / 'examples/paper-review-ledger/summary-check.json'), cwd=temp,
        ).stdout)
        if summary_result['paper_error_established']:
            raise RuntimeError('installed summary-check smoke check failed')
        scaffold = temp / 'agent-scaffold'
        run(str(cli), 'scaffold', 'finite_map_fixed_point', '--output', str(scaffold), cwd=temp)
        checked = json.loads(run(str(cli), 'validate-intake', str(scaffold / 'audit.json'), cwd=temp).stdout)
        if checked['valid'] is not True or checked['source_provenance'] != 'NOT_AUTHENTICATED':
            raise RuntimeError('installed scaffold/validate-intake smoke check failed')

        summary = {
            'version': version,
            'python': sys.version.split()[0],
            'tests': tests.stdout.strip().splitlines()[-1],
            'synthetic_cases': bench['case_count'],
            'synthetic_matched': bench['matched'],
            'mvp_real_cases': real['cases'],
            'mvp_real_matched': real['matched'],
            'trusted_core_static_scan': 'PASS',
            'source_checksums': 'PASS',
            'schema_drift': 'PASS',
            'intake_schema_drift': 'PASS',
            'review_schema_drift': 'PASS',
            'summary_schema_drift': 'PASS',
            'paper_audit_schema_drift': 'PASS',
            'paper_audit_development_results': 'PASS',
            'capability_examples_drift': 'PASS',
            'frozen_screen_review': 'PASS',
            'compileall': 'PASS',
            'wheel_sha256': sha256(wheel),
            'wheel_reproducible': 'PASS',
            'wheel_install_smoke': 'PASS',
            'agent_cli_smoke': 'PASS',
            'review_summary_cli_smoke': 'PASS',
            'paper_audit_cli_smoke': 'PASS',
            'runtime_dependencies': pyproject['project'].get('dependencies', []),
        }
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
