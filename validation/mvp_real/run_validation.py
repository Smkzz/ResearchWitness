from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
expected = {
    'elliptic-c4': ('FORMALIZATION_COUNTEREXAMPLE_VERIFIED', 'NOT_READY', 40, 'quadratic_nonquartic'),
    'elliptic-c7': ('FORMALIZATION_COUNTEREXAMPLE_VERIFIED', 'NOT_READY', 20, 'quartic_residue'),
    'fixed-point': ('FORMALIZATION_COUNTEREXAMPLE_VERIFIED', 'NOT_READY', None, None),
}
results = {}
with tempfile.TemporaryDirectory(prefix='researchwitness-real-') as td:
    out = Path(td)
    for name, exp in expected.items():
        case_out = out / name
        html = out / f'{name}.html'
        proc = subprocess.run([sys.executable, '-m', 'researchwitness', 'audit', str(HERE/name/'audit.json'),
                               '--output', str(case_out), '--html', str(html), '--as-of', '2026-10-04'],
                              cwd=ROOT, text=True, capture_output=True, check=True)
        data=json.loads(proc.stdout)
        report=data['report']; ready=data['contact_readiness']
        assert report['decision']==exp[0]
        assert ready['status']==exp[1]
        assert ready['author_contact_authorized'] is False
        assert report['paper_error_established'] is False
        assert html.is_file() and html.stat().st_size > 100
        if name.startswith('elliptic'):
            detail=report['formalization_result']['detail']
            assert detail['total_solution_count']==exp[2]
            assert detail['power_class']==exp[3]
        else:
            assert report['formalization_result']['detail']['fixed_points']==[]
            assert 'OPEN_OBJECTION' in {f['code'] for f in report['context_flags']}
        results[name]={'decision':report['decision'],'contact_readiness':ready['status'],
                       'detail':report['formalization_result']['detail'],
                       'context_flags':[f['code'] for f in report['context_flags']]}
print(json.dumps({'cases':len(results),'matched':len(results),'results':results},indent=2))
