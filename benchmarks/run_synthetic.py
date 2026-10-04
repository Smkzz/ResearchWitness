"""Seeded engineering conformance scenarios, NOT a paper-discovery benchmark."""
from copy import deepcopy
from datetime import date
from fractions import Fraction as F
from pathlib import Path
from collections import Counter
import json
import platform
import random
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from researchwitness import evaluate, Invalid
from researchwitness.checkers import check
from researchwitness.capsule import core_digest
from researchwitness.strict import digest
from tools.make_examples import base_case, write_case

SEED = 20261004


def run(out: Path) -> dict:
    started = time.perf_counter()
    rng = random.Random(SEED)
    records = []
    def record(group, key, expected, actual, inputs):
        records.append({'id':f'{group}-{key:03d}', 'group':group, 'expected':expected, 'actual':actual,
                        'matches':expected==actual, 'input_sha256':digest(inputs)})
    for i in range(100):
        a,b,c = [rng.randint(-7,7) for _ in range(3)]
        x,y = F(rng.randint(-50,50),10),F(rng.randint(-50,50),10)
        # Oracle in factored form; checker receives the six-term expanded polynomial.
        value = (a*x+b*y+c)**2
        terms = [{'coefficient':str(v),'powers':p} for v,p in
                 [(a*a,{'x':2}),(b*b,{'y':2}),(2*a*b,{'x':1,'y':1}),
                  (2*a*c,{'x':1}),(2*b*c,{'y':1}),(c*c,{})]]
        domain={v:{'lower':'-5','upper':'5','lower_closed':True,'upper_closed':True} for v in ('x','y')}
        witness={'kind':'polynomial_upper_bound','point':{'x':str(x),'y':str(y)}}
        for sign,group,expected in [(-1,'polynomial-positive','REFUTED_FOR_FORMALIZATION'),
                                    (1,'polynomial-nonrefuting','NO_REFUTATION_AT_WITNESS')]:
            spec={'kind':'polynomial_upper_bound','domain':domain,'terms':terms,'upper_bound':str(value+F(sign,1000))}
            actual=check(spec,witness)['status']
            record(group,i,expected,actual,{'spec':spec,'witness':witness})
        bad=deepcopy(witness); bad['point']['x']='6'
        try: actual=check(spec,bad)['status']
        except Invalid: actual='INVALID'
        record('infeasible-witness',i,'INVALID',actual,{'spec':spec,'witness':bad})
    for i in range(100):
        a,b,c = [F(rng.randint(1,50),rng.randint(1,20)) for _ in range(3)]
        # Square radicands have known rational roots, independent of the isqrt implementation.
        left=a-b+c
        sign=-1 if i%2 else 1
        spec={'kind':'scalar_radical_comparison',
              'left':{'constant':str(c),'terms':[{'coefficient':'1','radicand':str(a*a)},
                                                {'coefficient':'-1','radicand':str(b*b)}]},
              'upper_bound':{'constant':str(left+F(sign,1000)),'terms':[]}}
        witness={'kind':'scalar_radical_comparison'}
        expected='REFUTED_FOR_FORMALIZATION' if sign==-1 else 'NO_REFUTATION_AT_WITNESS'
        record('radical-signed',i,expected,check(spec,witness)['status'],{'spec':spec,'witness':witness})
    gate_kinds=(
        'baseline','source-unverified','correction-present','future-correction-check',
        'stale-correction-check','objection','unchecked-correction','legacy-field',
        'hash-tamper','quote-tamper'
    )
    expected_flags={
        'source-unverified':'SOURCE_CAPTURE_UNVERIFIED',
        'correction-present':'CORRECTION_PRESENT',
        'future-correction-check':'FUTURE_CORRECTION_CHECK',
        'stale-correction-check':'STALE_CORRECTION_CHECK',
        'objection':'OPEN_OBJECTION',
        'unchecked-correction':'CORRECTION_STATUS_UNCHECKED',
    }
    for i in range(100):
        variant=gate_kinds[i%len(gate_kinds)]
        with tempfile.TemporaryDirectory(prefix='researchwitness-conformance-') as tmp:
            case,data=base_case(); case['case_id']=f'synthetic-conformance-{i}'
            if variant=='source-unverified': case['source']['capture_status']='unverified'
            elif variant=='correction-present': case['source']['correction_check']['status']='present'
            elif variant=='future-correction-check': case['source']['correction_check']['checked_on']='2026-10-05'
            elif variant=='stale-correction-check': case['source']['correction_check']['checked_on']='2026-01-01'
            elif variant=='objection': case['unresolved_objections']=['Synthetic applicability objection.']
            elif variant=='unchecked-correction': case['source']['correction_check']['status']='unchecked'
            elif variant=='legacy-field': case['reviews']=[]
            elif variant=='quote-tamper': case['claim']['anchor']['quote']='Not present in captured source.'
            write_case(tmp,case,data)
            if variant=='hash-tamper':
                (Path(tmp)/'source.txt').write_text('An altered source.')
            try:
                result=evaluate(tmp,date(2026,10,4))
                if result['paper_error_established'] or result['external_actions']!='OUT_OF_SCOPE':
                    raise RuntimeError('Scope invariant violated')
                if variant in expected_flags:
                    code=expected_flags[variant]
                    actual=('FLAG:'+code if code in {x['code'] for x in result['context_flags']}
                            else 'MISSING_FLAG:'+code)
                    expected='FLAG:'+code
                else:
                    actual=result['decision']
                    expected='FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
            except Invalid:
                actual='INVALID'
                expected='INVALID' if variant in ('legacy-field','hash-tamper','quote-tamper') else 'UNEXPECTED_INVALID'
            record('context-'+variant,i,expected,actual,case)
    summary={'classification':'SYNTHETIC ENGINEERING CONFORMANCE, NOT SCIENTIFIC DISCOVERY EVALUATION',
             'seed':SEED,'case_count':len(records),'matched':sum(r['matches'] for r in records),
             'mismatches':[r for r in records if not r['matches']],
             'group_counts':dict(Counter(r['group'] for r in records)),
             'outcome_counts':dict(Counter(r['actual'] for r in records)),
             'core_sha256':core_digest(), 'python':platform.python_version(),
             'wall_seconds':round(time.perf_counter()-started,6),
             'paper_discovery_precision':'NOT_MEASURED','paper_discovery_recall':'NOT_MEASURED',
             'false_contact_rate':'NOT_ESTIMATED','independence':'Cases share generators; not independent clinical/scientific trials.'}
    out.mkdir(parents=True,exist_ok=True)
    (out/'synthetic-scenarios.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in records))
    (out/'synthetic-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    if summary['mismatches']: raise RuntimeError('Conformance mismatch')
    return summary


if __name__=='__main__':
    print(json.dumps(run(Path(__file__).resolve().parents[1]/'evidence'),indent=2))
