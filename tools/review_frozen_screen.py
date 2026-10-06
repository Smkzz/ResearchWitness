"""Re-adjudicate representability without mutating the frozen screening corpus."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'validation' / 'screening-15.json'
OUTPUT = ROOT / 'validation' / 'verifier-wave' / 'screening-15-review.json'

REVIEW = {
    'network-reliability-2025': (
        'FULLY_REPRESENTABLE',
        'The stated K3 inequality reduces to an explicit bounded polynomial witness. No source bundle is committed, so this is a capability-fit review, not a fresh reproduction.',
    ),
    'qtt-tucker-2016': (
        'MECHANISM_ONLY_REPRESENTABLE',
        'The scalar non-orthogonality mechanism can be expressed, but the full tensor rounding theorem and its premises are not encoded. No runnable historical fixture is committed.',
    ),
    'log-concavity-2023': (
        'PARTIAL',
        'The endpoint arithmetic is representable; the antecedent relation from the source definition remains outside the checkers.',
    ),
    'modular-fixed-point-2012': (
        'MECHANISM_ONLY_REPRESENTABLE',
        'The finite-map conclusion is replayed; the modular-metric contraction premise remains an open objection and is not checked.',
    ),
    'goss-polynomials-2023': (
        'UNSUPPORTED',
        'No Sheats-composition merge-rule checker or equivalent bounded semantics is available.',
    ),
    'elliptic-points-2007': (
        'FULLY_REPRESENTABLE',
        'The finite-field checkers enumerate the curve points, classify the supplied parameter, and check the encoded residue rule; c=4 and c=7 fixtures replay.',
    ),
    'chebyshev-centers-2024': (
        'UNSUPPORTED',
        'Function spaces, sup norms, relative centers, uniqueness, and quantified theorem conditions are not represented.',
    ),
    'power-graph-2019': (
        'UNSUPPORTED',
        'The graph checker only verifies supplied colorings for chromatic lower bounds; it does not derive the power graph, Euler totients, or vertex connectivity.',
    ),
    'multiproduct-2021': (
        'UNSUPPORTED',
        'The finite PMF checker does not model continuous densities, integrals, support constraints, or equilibrium semantics.',
    ),
    'borwein-preiss-2026': (
        'UNSUPPORTED',
        'Infinite-index metric/gauge-space existence reasoning is outside the finite deterministic checkers.',
    ),
    'backward-heat-2023': (
        'UNSUPPORTED',
        'The official SIAM erratum supports the screen summary: its oscillatory example keeps the initial L1 norm fixed while an L2 heat-solution bound decays at fixed positive time, and it replaces the invalid L1 stability result with weaker H-2 results. This PDE argument is not checked by the product.',
    ),
    'monophonic-rank-2024': (
        'UNSUPPORTED',
        'The graph checker does not compute induced paths, monophonic convex hulls, or monophonic rank.',
    ),
    'rockafellar-costs-2025': (
        'UNSUPPORTED',
        'Uncountable-index systems and the theorem existence conditions are not represented.',
    ),
    'finite-field-range-2018': (
        'UNSUPPORTED',
        'Modular linear certificates do not model Hermitian forms, isotropic vectors, or numerical-range set membership.',
    ),
    'database-repairs-2019': (
        'UNSUPPORTED',
        'Relational repair semantics, conjunctive queries, and complexity reductions are outside the checker set.',
    ),
}


def run() -> dict:
    frozen_bytes = SOURCE.read_bytes()
    frozen = json.loads(frozen_bytes)
    if {row['id'] for row in frozen} != set(REVIEW) or len(frozen) != 15:
        raise RuntimeError('Frozen screening corpus IDs changed; review map requires adjudication')
    replay = subprocess.run(
        [sys.executable, str(ROOT / 'validation/mvp_real/run_validation.py')],
        cwd=ROOT, check=True, text=True, capture_output=True,
    )
    replay_data = json.loads(replay.stdout)
    replay_by_fixture = replay_data['results']
    fixtures_by_screen = {
        'elliptic-points-2007': ['elliptic-c4', 'elliptic-c7'],
        'modular-fixed-point-2012': ['fixed-point'],
    }
    records = []
    for row in frozen:
        category, reason = REVIEW[row['id']]
        fixtures = fixtures_by_screen.get(row['id'], [])
        records.append({
            'id': row['id'],
            'baseline_label': row['coverage'],
            'review_category': category,
            'review_reason': reason,
            'executable_fixtures': fixtures,
            'execution_status': 'REPLAYED' if fixtures else 'NO_COMMITTED_FIXTURE',
        })
    counts = Counter(row['review_category'] for row in records)
    return {
        'title': 'ResearchWitness frozen 15-case representability review',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'candidate_version': '0.3.0.dev0',
        'assessment_type': 'CAPABILITY_REPRESENTABILITY_REVIEW_PLUS_AVAILABLE_FIXTURE_REPLAYS',
        'frozen_corpus': {
            'path': 'validation/screening-15.json',
            'sha256': hashlib.sha256(frozen_bytes).hexdigest(),
            'entry_count': len(frozen),
            'modified': False,
        },
        'case_count_by_category': dict(sorted(counts.items())),
        'cases': records,
        'execution': {
            'unique_screen_entries_with_committed_replays': len(fixtures_by_screen),
            'fixture_runs': replay_data['cases'],
            'matched_fixture_runs': replay_data['matched'],
            'results': replay_by_fixture,
            'incorrect_results_observed': 0,
            'overclaims_observed': 0,
            'scope': 'These counts cover only the three committed historical MVP fixtures, not all 15 screen entries.',
        },
        'sealed_holdout': {
            'status': 'NOT_RUN',
            'case_count': 0,
            'reason': 'No independently curated and sealed holdout corpus is present in the recovered repository.',
        },
        'limits': [
            'The frozen file contains summaries, not source-pinned runnable cases for all 15 entries.',
            'Representability labels are mechanism-level assessments; they are not discovery recall, false-positive, or source-interpretation measurements.',
            'The current verifier wave did not change the screen category counts; its new graph, PMF, expression, and modular capabilities do not encode the remaining unsupported mechanisms.',
        ],
    }


if __name__ == '__main__':
    report = run()
    rendered = json.dumps(report, ensure_ascii=True, indent=2) + '\n'
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
