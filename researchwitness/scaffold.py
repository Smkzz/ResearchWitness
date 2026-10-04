"""Create editable, explicitly synthetic agent-intake scaffolds."""
from __future__ import annotations

import json
from pathlib import Path

from .checkers import KINDS
from .example_data import capability_examples
from .strict import Invalid


def scaffold(kind: str, output: Path | str) -> Path:
    if kind not in KINDS:
        raise Invalid('Unsupported proof kind')
    sample = capability_examples()[kind]
    root = Path(output).absolute()
    root.mkdir(parents=True, exist_ok=False)

    quote = sample['statement']
    (root / 'source.txt').write_text(
        quote + '\nSYNTHETIC SCAFFOLD EXAMPLE. Replace with the pinned source text.\n',
        encoding='utf-8',
    )
    (root / 'correction-check.txt').write_text(
        'No correction search has been performed. Replace this file with dated search evidence.\n',
        encoding='utf-8',
    )
    intake = {
        'intake_version': '0.1',
        'case_id': f'scaffold-{kind}',
        'source': {
            'identifier': 'synthetic:replace-with-source-identifier',
            'version': 'template-v1',
            'text_file': 'source.txt',
            'capture_status': 'synthetic',
            'correction_check': {
                'checked_on': '2000-01-01',
                'status': 'unchecked',
                'evidence_file': 'correction-check.txt',
            },
        },
        'claim': {
            'id': 'C1',
            'statement': sample['statement'],
            'scope': sample['scope'],
            'assumptions': sample['assumptions'],
            'excluded_claims': sample['excluded_claims'],
            'quote': quote,
            'formalization': sample['formalization'],
        },
        'witness': sample['witness'],
        'unresolved_objections': [
            'Scaffold data is synthetic; source interpretation and correction status require review.'
        ],
    }
    (root / 'audit.json').write_text(
        json.dumps(intake, ensure_ascii=True, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    (root / 'README.txt').write_text(
        'Synthetic ResearchWitness intake scaffold.\n'
        'Replace the source, version, quote, claim, formalization, witness, assumptions, and correction search.\n'
        'The source is marked synthetic and the correction search unchecked by design.\n'
        'Run: researchwitness validate-intake audit.json\n'
        'Then: researchwitness prepare audit.json --output evidence-bundle\n'
        'A verified formalization result does not authenticate the source or prove a paper-level error.\n',
        encoding='utf-8',
    )
    return root
