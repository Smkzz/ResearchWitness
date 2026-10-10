from __future__ import annotations
import json
import hashlib
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
BUDGET = Path(__file__).with_name('jats-performance-budget-20261010.json')
MEASURED_SOURCE_FILES = (
    'researchwitness/jats.py',
    'researchwitness/denominator_provenance.py',
    'researchwitness/table_arithmetic.py',
)
CASES = {
    'small_valid': (20_480, 200),
    'medium_valid': (1_048_576, 5_000),
    'entity_expansion': (1_048_576, 5_000),
    'large_valid': (8_388_608, 10_000),
}
EXPECTED_VALID_RELATIONS = {case: rows for case, (_size, rows) in CASES.items()}
MALFORMED_DEPTH_REJECTION = 'JATS source exceeded the configured nesting limit'


def make_source(target_bytes: int, row_count: int, entity_tokens: int = 0) -> bytes:
    rows = ''.join(
        f'<tr><th scope="row">Event {index}</th><td>1 (5%)</td></tr>'
        for index in range(row_count)
    )
    prefix = '<article><body><p>' + '&euro;' * entity_tokens
    suffix = (
        '</p><table-wrap id="synthetic-performance"><table><thead><tr>'
        '<th>Outcome</th><th>All participants (N=20)</th></tr></thead><tbody>'
        + rows + '</tbody></table></table-wrap></body></article>'
    )
    pad = max(0, target_bytes - len((prefix + suffix).encode('utf-8')))
    source = (prefix + 'x' * pad + suffix).encode('utf-8')
    if len(source) > target_bytes:
        raise RuntimeError(f'Generated source {len(source)} exceeded {target_bytes}')
    return source


def malformed_source() -> bytes:
    base = b'<article>' + b'<x>' * 80 + b'</x>' * 80 + b'</article>'
    return base + b' ' * (1024 - len(base))


def measure(case: str) -> dict[str, object]:
    sys.path.insert(0, str(REPO))
    from researchwitness.jats import parse_jats
    from researchwitness.strict import Invalid
    from researchwitness.table_arithmetic import check_structured_table_percentages

    if case == 'malformed_depth':
        source = malformed_source()
    elif case == 'entity_expansion':
        source = make_source(*CASES[case], entity_tokens=10_000)
    else:
        source = make_source(*CASES[case])
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    try:
        document = parse_jats(source)
        result = check_structured_table_percentages(document)
        status = 'parsed_and_checked'
        relations = len(result['relations'])
        expected_relations = EXPECTED_VALID_RELATIONS.get(case)
        if expected_relations is None:
            raise AssertionError(f'{case} unexpectedly parsed instead of being rejected')
        if relations != expected_relations:
            raise AssertionError(
                f'{case} produced {relations} relations; expected {expected_relations}'
            )
        if result['checked_cells'] != expected_relations or any(
            item['status'] != 'ELIGIBLE_CHECKED_MATCH' for item in result['relations']
        ):
            raise AssertionError(f'{case} did not produce the expected checked matches')
    except Invalid as exc:
        if case != 'malformed_depth' or str(exc) != MALFORMED_DEPTH_REJECTION:
            raise
        status = 'rejected_by_configured_nesting_limit'
        relations = 0
    if case == 'malformed_depth' and status != 'rejected_by_configured_nesting_limit':
        raise AssertionError('malformed_depth did not fail at the configured nesting limit')
    wall = time.perf_counter() - started_wall
    cpu = time.process_time() - started_cpu
    return {
        'case': case,
        'input_bytes': len(source),
        'rows': CASES[case][1] if case in CASES else 0,
        'entity_tokens': 10_000 if case == 'entity_expansion' else 0,
        'status': status,
        'relations': relations,
        'wall_seconds': wall,
        'cpu_seconds': cpu,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def main() -> None:
    if sys.platform != 'linux':
        raise RuntimeError('This diagnostic uses Linux ru_maxrss units and is qualified on Linux only')
    if len(sys.argv) == 3 and sys.argv[1] == '--measure':
        print(json.dumps(measure(sys.argv[2]), sort_keys=True))
        return
    results = {}
    for case in (*CASES.keys(), 'malformed_depth'):
        samples = []
        for _ in range(5):
            completed = subprocess.run(
                [PYTHON, str(Path(__file__).resolve()), '--measure', case],
                cwd=REPO, check=True, capture_output=True, text=True,
            )
            samples.append(json.loads(completed.stdout))
        wall = [float(item['wall_seconds']) for item in samples]
        cpu = [float(item['cpu_seconds']) for item in samples]
        results[case] = {
            'input_bytes': samples[0]['input_bytes'],
            'rows': samples[0]['rows'],
            'entity_tokens': samples[0]['entity_tokens'],
            'status': samples[0]['status'],
            'relations': samples[0]['relations'],
            'median_wall_seconds': statistics.median(wall),
            'max_wall_seconds': max(wall),
            'median_cpu_seconds': statistics.median(cpu),
            'max_cpu_seconds': max(cpu),
            'max_peak_rss_kib': max(int(item['peak_rss_kib']) for item in samples),
            'samples': samples,
        }
        expected_status = (
            'rejected_by_configured_nesting_limit'
            if case == 'malformed_depth' else 'parsed_and_checked'
        )
        expected_relations = EXPECTED_VALID_RELATIONS.get(case, 0)
        if any(
            item['status'] != expected_status or item['relations'] != expected_relations
            for item in samples
        ):
            raise RuntimeError(f'{case} samples did not match their declared expected outcome')
    budget_bytes = BUDGET.read_bytes()
    budget = json.loads(budget_bytes)
    for case, result in results.items():
        limits = budget['limits'][case]
        result['within_declared_budget'] = (
            result['max_wall_seconds'] <= limits['max_wall_seconds']
            and result['max_cpu_seconds'] <= limits['max_cpu_seconds']
            and result['max_peak_rss_kib'] <= limits['max_peak_rss_kib']
        )
    report = {
    'purpose': 'Synthetic single-process JATS parse plus table-percentage diagnostic, including named-entity offset mapping.',
        'limitations': [
            'synthetic inputs only', 'single-process and single-table',
            'Linux only; no Windows measurements', 'no disk or export measurements',
            'no concurrency, startup, shutdown, retry, or cancellation measurements',
            'does not establish production workload performance',
        ],
        'python': subprocess.check_output([PYTHON, '--version'], text=True).strip(),
        'platform': sys.platform,
        'budget_file': BUDGET.name,
        'budget_sha256': hashlib.sha256(budget_bytes).hexdigest(),
        'budget': budget,
        'benchmark_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'measured_source_sha256': {
            path: hashlib.sha256((REPO / path).read_bytes()).hexdigest()
            for path in MEASURED_SOURCE_FILES
        },
        'cases': results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if not all(result['within_declared_budget'] for result in results.values()):
        raise SystemExit('one or more synthetic workloads exceeded the predeclared budget')

if __name__ == '__main__':
    main()
