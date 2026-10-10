"""Measure bounded checker workloads; this is not a paper-discovery benchmark."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import itertools
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from researchwitness.checkers import check
from researchwitness.capsule import core_digest
from researchwitness.strict import digest


def workloads() -> dict[str, tuple[dict, dict, str]]:
    vars8 = [f'x{i}' for i in range(8)]
    leaves = [{'op': 'const', 'value': '1'} for _ in range(128)]
    while len(leaves) > 1:
        leaves = [{'op': 'add', 'args': [leaves[i], leaves[i + 1]]}
                  for i in range(0, len(leaves), 2)]
    graph_vertices = [f'v{i}' for i in range(256)]
    graph_edges = []
    for left in graph_vertices[:128]:
        for right in graph_vertices[128:]:
            graph_edges.append([left, right])
            if len(graph_edges) == 8192:
                break
        if len(graph_edges) == 8192:
            break
    graph_coloring = {name: ('red' if i < 128 else 'blue')
                      for i, name in enumerate(graph_vertices)}
    pmf_variables = [f'x{i}' for i in range(8)]
    pmf_domains = {name: ['0', '1'] for name in pmf_variables}
    atoms = [
        {'assignment': dict(zip(pmf_variables, state)), 'probability': '1/256'}
        for state in itertools.product(('0', '1'), repeat=8)
    ]
    field_terms = [{'coefficient': 0, 'powers': {}} for _ in range(3)]

    profiles = {
        'scalar_radical_32_terms': (
            {'kind': 'scalar_radical_comparison',
             'left': {'constant': '0', 'terms': [
                 {'coefficient': '1', 'radicand': '2'} for _ in range(32)]},
             'upper_bound': {'constant': '0', 'terms': []}},
            {'kind': 'scalar_radical_comparison'},
            '32 radical terms; exact rational inputs; 40-digit certified enclosures',
        ),
        'polynomial_8_variables_64_terms': (
            {'kind': 'polynomial_upper_bound',
             'domain': {name: {'lower': '0', 'upper': '1', 'lower_closed': True,
                               'upper_closed': True} for name in vars8},
             'terms': [{'coefficient': '1/97', 'powers': {'x0': 1}} for _ in range(64)],
             'upper_bound': '0'},
            {'kind': 'polynomial_upper_bound', 'point': {name: '1' for name in vars8}},
            '8 variables; 64 degree-1 terms; exact rational point',
        ),
        'rational_expression_255_nodes': (
            {'kind': 'rational_expression_upper_bound',
             'domain': {'x': {'lower': '0', 'upper': '1', 'lower_closed': True,
                              'upper_closed': True}},
             'expression': leaves[0], 'upper_bound': '127'},
            {'kind': 'rational_expression_upper_bound', 'point': {'x': '0'}},
            '255 expression nodes; depth 8; exact rational values',
        ),
        'finite_map_256_elements': (
            {'kind': 'finite_map_fixed_point', 'universe': [str(i) for i in range(256)],
             'conclusion': 'has_fixed_point'},
            {'kind': 'finite_map_fixed_point',
             'mapping': {str(i): str((i + 1) % 256) for i in range(256)}},
            '256-element explicit self-map',
        ),
        'finite_graph_256_vertices_8192_edges': (
            {'kind': 'finite_graph_chromatic_lower_bound', 'vertices': graph_vertices,
             'edges': graph_edges, 'minimum_colors': 3},
            {'kind': 'finite_graph_chromatic_lower_bound', 'coloring': graph_coloring},
            '256 vertices; 8,192 edges; supplied proper 2-coloring',
        ),
        'finite_pmf_256_states_64_clauses': (
            {'kind': 'finite_pmf_bound', 'operation': 'probability',
             'domains': pmf_domains, 'event': [{'x0': '0'} for _ in range(64)],
             'relation': 'at_most', 'bound': '1/4'},
            {'kind': 'finite_pmf_bound', 'atoms': atoms},
            '8 binary variables; 256 joint states; 64 event clauses',
        ),
        'modular_system_16_by_16': (
            {'kind': 'modular_linear_system', 'modulus': 4096,
             'matrix': [[int(i == j) for j in range(16)] for i in range(16)],
             'rhs': [0] * 16, 'conclusion': 'no_solution'},
            {'kind': 'modular_linear_system',
             'certificate': {'type': 'solution', 'vector': [0] * 16}},
            'modulus 4,096; 16 equations; 16 variables; 256 matrix entries',
        ),
    }
    finite_field_base = {
        'prime': 113, 'variables': ['x', 'y', 'z'], 'point_count_adjustment': 0,
        'modulus': 2, 'terms': field_terms,
    }
    profiles['finite_field_4_3m_term_evaluations'] = (
        {'kind': 'finite_field_polynomial_residue', **finite_field_base,
         'parameters': [], 'allowed_residues': [0]},
        {'kind': 'finite_field_polynomial_residue', 'parameters': {}},
        '113^3 = 1,442,897 points; 3 terms; 4,328,691 point-term evaluations',
    )
    profiles['finite_field_power_rule_4_3m_term_evaluations'] = (
        {'kind': 'finite_field_quadratic_quartic_residue_rule', **finite_field_base,
         'parameters': ['c'], 'classification_parameter': 'c',
         'expected_residues': {
             'quartic_residue': [0], 'quadratic_nonquartic': [0], 'quadratic_nonresidue': [0],
         }},
        {'kind': 'finite_field_quadratic_quartic_residue_rule', 'parameters': {'c': 1}},
        '113^3 = 1,442,897 points; 3 terms; 4,328,691 point-term evaluations',
    )
    return profiles


EXPECTED_RESULT_STATUS = {
    'scalar_radical_32_terms': 'REFUTED_FOR_FORMALIZATION',
    'polynomial_8_variables_64_terms': 'REFUTED_FOR_FORMALIZATION',
    'rational_expression_255_nodes': 'REFUTED_FOR_FORMALIZATION',
    'finite_map_256_elements': 'REFUTED_FOR_FORMALIZATION',
    'finite_graph_256_vertices_8192_edges': 'REFUTED_FOR_FORMALIZATION',
    'finite_pmf_256_states_64_clauses': 'REFUTED_FOR_FORMALIZATION',
    'modular_system_16_by_16': 'REFUTED_FOR_FORMALIZATION',
    'finite_field_4_3m_term_evaluations': 'REFUTED_FOR_FORMALIZATION',
    'finite_field_power_rule_4_3m_term_evaluations': 'REFUTED_FOR_FORMALIZATION',
}


def run(repeats: int = 3) -> dict:
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        raise ValueError('repeats must be a positive integer')
    results = []
    profiles = workloads()
    if set(profiles) != set(EXPECTED_RESULT_STATUS):
        raise RuntimeError('performance workload and expected-status registries differ')
    for name, (formalization, witness, workload) in profiles.items():
        expected_status = EXPECTED_RESULT_STATUS[name]
        warmup = check(formalization, witness)  # warm-up and validation outside timing sample
        if not isinstance(warmup, dict) or warmup.get('status') != expected_status:
            raise RuntimeError(f'checker returned an unexpected warm-up status for workload {name}')
        timings = []
        output = None
        for _ in range(repeats):
            started = time.perf_counter()
            output = check(formalization, witness)
            timings.append((time.perf_counter() - started) * 1000)
            if not isinstance(output, dict) or output.get('status') != expected_status:
                raise RuntimeError(f'checker status changed during workload {name}')
        results.append({
            'name': name,
            'workload': workload,
            'formalization_witness_sha256': digest({'formalization': formalization, 'witness': witness}),
            'expected_checker_kind': formalization['kind'],
            'result_status': output['status'],
            'repeats': repeats,
            'median_ms': round(statistics.median(timings), 3),
            'minimum_ms': round(min(timings), 3),
            'maximum_ms': round(max(timings), 3),
        })
    return {
        'classification': 'BOUNDED CHECKER PERFORMANCE PROFILE, NOT SCIENTIFIC DISCOVERY EVALUATION',
        'measured_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'python': platform.python_version(),
        'platform': platform.platform(),
        'core_sha256': core_digest(),
        'repeats_per_workload': repeats,
        'results': results,
        'limitations': [
            'Wall times depend on the machine, Python build, and concurrent load.',
            'The workloads target checker limits and do not measure agent discovery or source interpretation.',
            'Resource caps, not these wall-time samples, define accepted input size.',
        ],
    }


if __name__ == '__main__':
    def positive_int(value: str) -> int:
        parsed = int(value)
        if parsed < 1:
            raise argparse.ArgumentTypeError('must be a positive integer')
        return parsed

    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--repeats', type=positive_int, default=3)
    args = parser.parse_args()
    report = run(args.repeats)
    rendered = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
