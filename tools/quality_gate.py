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
                if roots & BANNED_IMPORT_ROOTS:
                    raise RuntimeError(f'banned import in trusted core: {path.name}: {roots & BANNED_IMPORT_ROOTS}')
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split('.')[0]
                if root in BANNED_IMPORT_ROOTS:
                    raise RuntimeError(f'banned import in trusted core: {path.name}: {root}')
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                    raise RuntimeError(f'banned dynamic call in trusted core: {path.name}: {node.func.id}')


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
    from tools.write_schema import make as make_schema, make_intake_schema
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
    if json.loads((ROOT / 'researchwitness/capability_examples.json').read_text()) != build_capability_examples(ROOT / 'examples'):
        raise RuntimeError('packaged capability example drift')
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
        dist.mkdir()
        dist2.mkdir()
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
        # RW-MATH-02: exercise source -> typed model -> exact certificate from
        # the installed wheel OUTSIDE the checkout. All sources are synthetic.
        from researchwitness.exact_optimization import canonical_bytes
        from tools.optimization_examples import bilinear_half
        claims = ROOT / 'examples/source-claim-v1'
        source_path = claims / 'bilinear.txt'
        hints_path = claims / 'bilinear-hints.json'
        model_path = temp / 'source-claim-model.json'
        candidate_path = temp / 'source-claim-candidate.json'
        exact_compile = json.loads(run(
            str(python), '-m', 'researchwitness.source_claim_workflow', 'compile',
            '--source', str(source_path), '--expected-source-sha256', sha256(source_path),
            '--hints', str(hints_path), '--expected-hints-sha256', sha256(hints_path),
            '--output-model', str(model_path), '--output-candidate', str(candidate_path),
            cwd=temp,
        ).stdout)
        if exact_compile['mathematical_proof'] != 'not_supplied':
            raise RuntimeError('installed source compiler incorrectly claims proof')
        fixture = bilinear_half()
        if json.loads(model_path.read_text(encoding='utf-8')) != fixture['model']:
            raise RuntimeError('source compiled to a different exact mathematical model')
        cert_path = temp / 'synthetic-bilinear-proof.jsonl'
        cert_path.write_bytes(canonical_bytes(fixture['header']) + b''.join(
            canonical_bytes(leaf) for leaf in fixture['leaves']))
        verified = json.loads(run(
            str(python), '-m', 'researchwitness.source_claim_workflow', 'verify',
            '--source', str(source_path), '--expected-source-sha256', sha256(source_path),
            '--hints', str(hints_path), '--expected-hints-sha256', sha256(hints_path),
            '--model', str(model_path), '--expected-model-sha256', sha256(model_path),
            '--candidate', str(candidate_path), '--expected-candidate-sha256', sha256(candidate_path),
            '--certificate', str(cert_path), '--expected-certificate-sha256', sha256(cert_path),
            cwd=temp,
        ).stdout)
        if (verified['mathematical_model_upper_bound'] != '1/4'
                or not verified['source_span_rederived_exactly']
                or verified['paper_error_established'] is not False):
            raise RuntimeError('installed source-to-model exact proof mismatch')
        false_src = claims / 'refutable.txt'
        false_model = temp / 'source-false-model.json'
        false_candidate = temp / 'source-false-candidate.json'
        run(str(python), '-m', 'researchwitness.source_claim_workflow', 'compile',
            '--source', str(false_src), '--expected-source-sha256', sha256(false_src),
            '--output-model', str(false_model), '--output-candidate', str(false_candidate),
            cwd=temp)
        point_path = claims / 'refutable-point.json'
        refuted = json.loads(run(
            str(python), '-m', 'researchwitness.source_claim_workflow', 'refute',
            '--source', str(false_src), '--expected-source-sha256', sha256(false_src),
            '--model', str(false_model), '--expected-model-sha256', sha256(false_model),
            '--candidate', str(false_candidate), '--expected-candidate-sha256', sha256(false_candidate),
            '--point', str(point_path), '--expected-point-sha256', sha256(point_path),
            cwd=temp,
        ).stdout)
        if (refuted['strict_violation_margin'] != '1/2'
                or refuted['paper_error_established'] is not False):
            raise RuntimeError('installed formal counterexample mismatch')
        unsupported = claims / 'unsupported.txt'
        unsupported_probe = subprocess.run([
            str(python), '-m', 'researchwitness.source_claim_workflow', 'compile',
            '--source', str(unsupported), '--expected-source-sha256', sha256(unsupported),
            '--output-model', str(temp / 'unsupported-model.json'),
            '--output-candidate', str(temp / 'unsupported-candidate.json'),
        ], cwd=temp, capture_output=True, text=True, check=False)
        if unsupported_probe.returncode != 2 or unsupported_probe.stdout:
            raise RuntimeError('installed compiler accepted unsupported scientific prose')
        # RW-MATH-03: prove and refute only literal mathematical sentences
        # with exact source bytes; never promote contextual paper truth.
        prose_source = ROOT / 'examples/prose-math-v1/illustrative-source.txt'
        prose_report_path = temp / 'prose-math-report.json'
        prose_scan = json.loads(run(
            str(python), '-m', 'researchwitness.prose_math', 'scan',
            '--source', str(prose_source),
            '--expected-source-sha256', sha256(prose_source),
            '--output', str(prose_report_path), cwd=temp,
        ).stdout)
        prose_report = json.loads(prose_report_path.read_bytes())
        if (prose_scan['status'] != 'saved_candidate_screen'
                or prose_report['scan']['literal_candidates'] != 3
                or [entry['math']['formal_result'] for entry in prose_report['candidates']]
                != ['model_bound_supported', 'model_bound_refuted', 'model_bound_supported']
                or prose_report['scientific_accuracy_established'] is not False
                or any(entry['math']['paper_error_established'] is not False
                       for entry in prose_report['candidates'])):
            raise RuntimeError('installed literal prose math screening regression')
        prose_replayed = json.loads(run(
            str(python), '-m', 'researchwitness.prose_math', 'replay',
            '--source', str(prose_source),
            '--expected-source-sha256', sha256(prose_source),
            '--report', str(prose_report_path),
            '--expected-report-sha256', sha256(prose_report_path), cwd=temp,
        ).stdout)
        if (prose_replayed['status'] != 'exact_replay_complete'
                or prose_replayed['candidate_count'] != 3
                or prose_replayed['source_context_verified'] is not False):
            raise RuntimeError('installed literal prose math replay regression')
        # RW-MATH-04: same exact false literal in a declared assertion
        # and quotation, without asserting authorial intent or paper error.
        attribution_source = ROOT / 'examples/prose-attribution-v1/illustrative-source.txt'
        attribution_path = temp / 'source-declared-attribution.json'
        declared = json.loads(run(
            str(python), '-m', 'researchwitness.prose_attribution', 'scan',
            '--source', str(attribution_source),
            '--expected-source-sha256', sha256(attribution_source),
            '--output', str(attribution_path), cwd=temp,
        ).stdout)
        parsed = json.loads(attribution_path.read_bytes())
        blocks = parsed['context_blocks']
        if (declared['status'] != 'source_declared_context_report_saved'
                or len(blocks) != 2
                or blocks[0]['math'] != blocks[1]['math']
                or blocks[0]['interpretation'] != 'declared_asserted_literal_refuted'
                or blocks[1]['interpretation'] != 'declared_quoted_literal_refuted'
                or blocks[0]['math']['counterexample_margin'] != '1/2'
                or any(b['paper_error_established'] is not False
                       or b['author_intent_authenticated'] is not False for b in blocks)
                or parsed['whole_paper_meaning_verified'] is not False):
            raise RuntimeError('installed context-attribution negative control failed')
        replayed = json.loads(run(
            str(python), '-m', 'researchwitness.prose_attribution', 'replay',
            '--source', str(attribution_source),
            '--expected-source-sha256', sha256(attribution_source),
            '--report', str(attribution_path),
            '--expected-report-sha256', sha256(attribution_path), cwd=temp,
        ).stdout)
        if (replayed['status'] != 'source_declared_context_replayed'
                or replayed['context_block_count'] != 2
                or replayed['author_attribution_verified'] is not False):
            raise RuntimeError('installed source-declared attribution replay failed')
        changed_source = temp / 'source-context-swap.txt'
        changed_source.write_bytes(attribution_source.read_bytes().replace(
            b'role=quoted', b'role=asserted'))
        refused = subprocess.run([
            str(python), '-m', 'researchwitness.prose_attribution', 'scan',
            '--source', str(changed_source),
            '--expected-source-sha256', sha256(attribution_source),
        ], cwd=temp, capture_output=True, text=True, check=False)
        if refused.returncode != 2 or refused.stdout:
            raise RuntimeError('installed context source-swap was accepted')
        # Verify the independent installed-wheel JATS path outside the checkout.
        jats_dir = temp / 'installed-jats'
        jats = json.loads(run(str(cli), 'audit-jats',
                             str(ROOT / 'examples/synthetic-jats/article.xml'),
                             '--document-id', 'synthetic-jats', '--output-dir', str(jats_dir),
                             cwd=temp).stdout)
        if jats['summary'] != {'arithmetic_matches': 1, 'mismatch_candidates': 1,
                               'abstentions': 1}:
            raise RuntimeError('installed JATS audit smoke mismatch')
        replay = json.loads(run(str(cli), 'replay-jats', str(jats_dir),
                                '--expected-manifest-sha256', jats['manifest_sha256'],
                                cwd=temp).stdout)
        if replay['status'] != 'verified' or replay['findings_replayed'] != 3:
            raise RuntimeError('installed JATS replay smoke mismatch')
        structured_dir = temp / 'installed-structured-jats'
        structured = json.loads(run(
            str(cli), 'audit-jats', str(ROOT / 'examples/synthetic-jats/article.xml'), '--document-id',
            'synthetic-jats', '--output-dir', str(structured_dir),
            '--include-structure', cwd=temp,
        ).stdout)
        content = json.loads((structured_dir / 'report.json').read_bytes())
        if (len(content['table_projection']['tables']) != 2 or
                len(content['table_projection']['numeric_assertions']) != 3):
            raise RuntimeError('installed table projection smoke mismatch')
        reread = json.loads(run(
            str(cli), 'replay-jats', str(structured_dir),
            '--expected-manifest-sha256', structured['manifest_sha256'],
            cwd=temp,
        ).stdout)
        if reread['status'] != 'verified':
            raise RuntimeError('installed table replay mismatch')
        # Source-mapped crude-OR audit must run from the wheel, not the checkout.
        odds_dir = temp / 'installed-2x2-jats'
        odds = json.loads(run(str(cli), 'audit-jats',
                             str(ROOT / 'examples/synthetic-jats/odds-ratio.xml'),
                             '--document-id', 'synthetic-or', '--output-dir', str(odds_dir),
                             '--include-unadjusted-2x2', cwd=temp).stdout)
        or_report = json.loads((odds_dir / 'report.json').read_bytes())
        or_review = or_report['odds_ratio_review']
        if (not or_review['scan_complete'] or len(or_review['findings']) != 1
                or or_review['findings'][0]['recomputed_at_display_precision'] != '2.14'
                or or_report['paper_error_established'] is not False):
            raise RuntimeError('installed 2x2 source-mapping smoke mismatch')
        or_replay = json.loads(run(str(cli), 'replay-jats', str(odds_dir),
                                  '--expected-manifest-sha256', odds['manifest_sha256'],
                                  cwd=temp).stdout)
        if or_replay['status'] != 'verified':
            raise RuntimeError('installed 2x2 replay smoke mismatch')
        flow_dir = temp / 'installed-prose-flow'
        flow_result = json.loads(run(
            str(cli), 'audit-jats',
            str(ROOT / 'examples/synthetic-jats/prose-flow.xml'),
            '--document-id', 'synthetic-flow', '--output-dir', str(flow_dir),
            '--include-prose-flows', cwd=temp,
        ).stdout)
        flow_report = json.loads((flow_dir / 'report.json').read_bytes())
        if (flow_report['sample_flow_review']['candidate_count'] != 1
                or flow_report['sample_flow_review']['relations_mapped'] != 3
                or flow_report['paper_error_established'] is not False):
            raise RuntimeError('installed prose flow smoke mismatch')
        flow_replay = json.loads(run(
            str(cli), 'replay-jats', str(flow_dir),
            '--expected-manifest-sha256', flow_result['manifest_sha256'],
            cwd=temp,
        ).stdout)
        if flow_replay['status'] != 'verified':
            raise RuntimeError('installed prose-flow replay mismatch')
        stats_dir = temp / 'installed-se-statistics'
        stats = json.loads(run(
            str(cli), 'audit-jats', str(ROOT / 'examples/synthetic-jats/se-statistics.xml'),
            '--document-id', 'synthetic-statistics', '--output-dir', str(stats_dir),
            '--include-sd-se-n', cwd=temp,
        ).stdout)
        stats_report = json.loads((stats_dir / 'report.json').read_bytes())
        se = stats_report['statistical_se_review']
        if (not se['scan_complete'] or len(se['findings']) != 1
                or se['findings'][0]['recomputed_se_at_display_precision'] != '3.0'
                or stats_report['paper_error_established'] is not False):
            raise RuntimeError('installed SD/SE/n source mapping smoke mismatch')
        stats_replay = json.loads(run(
            str(cli), 'replay-jats', str(stats_dir),
            '--expected-manifest-sha256', stats['manifest_sha256'], cwd=temp,
        ).stdout)
        if stats_replay['status'] != 'verified':
            raise RuntimeError('installed SD/SE/n replay mismatch')
        # Verify the audit-only denominator provenance ledger from an installed
        # clean wheel, including unresolved relations and source replay.
        provenance_dir = temp / 'installed-denominator-trace'
        provenance = json.loads(run(
            str(cli), 'audit-jats',
            str(ROOT / 'examples/synthetic-jats/denominator-trace.xml'),
            '--document-id', 'synthetic-denominator',
            '--output-dir', str(provenance_dir), '--include-denominator-trace',
            cwd=temp,
        ).stdout)
        trace = json.loads((provenance_dir / 'report.json').read_bytes())[
            'denominator_evidence_trace'
        ]
        if (trace['relation_count'] != 3 or trace['unresolved_relation_count'] != 1
                or trace['full_article_denominator_provenance_established'] is not False
                or not any(f['detector_provenance_role'] == 'cell_ratio_denominator'
                           for row in trace['relations'] for f in row['denominator_facts'])):
            raise RuntimeError('installed denominator trace smoke mismatch')
        provenance_replay = json.loads(run(
            str(cli), 'replay-jats', str(provenance_dir),
            '--expected-manifest-sha256', provenance['manifest_sha256'],
            cwd=temp,
        ).stdout)
        if provenance_replay['status'] != 'verified':
            raise RuntimeError('installed denominator trace replay smoke mismatch')
        if smoke['paper_error_established'] or smoke['external_actions'] != 'OUT_OF_SCOPE':
            raise RuntimeError('scope invariant failed in installed wheel')
        capabilities = json.loads(run(str(cli), 'capabilities', '--json', cwd=temp).stdout)
        if len(capabilities['checkers']) != 10:
            raise RuntimeError('installed capability registry is incomplete')
        schema = json.loads(run(str(cli), 'schema', 'intake', cwd=temp).stdout)
        if schema['title'] != 'ResearchWitness agent intake 0.1':
            raise RuntimeError('installed intake schema command failed')
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
            'capability_examples_drift': 'PASS',
            'frozen_screen_review': 'PASS',
            'compileall': 'PASS',
            'wheel_sha256': sha256(wheel),
            'wheel_reproducible': 'PASS',
            'wheel_install_smoke': 'PASS',
            'agent_cli_smoke': 'PASS',
            'runtime_dependencies': pyproject['project'].get('dependencies', []),
        }
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
