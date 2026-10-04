"""MVP product layer: readiness and readable evidence output."""
from __future__ import annotations

from html import escape
import json
from typing import Any


def contact_readiness(report: dict[str, Any]) -> dict[str, Any]:
    """Assess whether a verified formalization is worth *user* review for author contact.

    This never authorizes contact. It only prevents obvious incomplete cases from looking ready.
    """
    blockers: list[str] = []
    if report['decision'] != 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED':
        blockers.append('NO_VERIFIED_COUNTEREXAMPLE')
    if report['source_capture_status'] != 'captured':
        blockers.append('SOURCE_NOT_CAPTURED')
    if report['correction_status'] != 'none_found':
        blockers.append('CORRECTION_STATUS_NOT_CLEAR')
    blocking_flags = {
        'FUTURE_CORRECTION_CHECK', 'STALE_CORRECTION_CHECK', 'CORRECTION_STATUS_UNCHECKED',
        'CORRECTION_PRESENT', 'EMPTY_CORRECTION_EVIDENCE', 'OPEN_OBJECTION', 'SYNTHETIC_SOURCE',
    }
    present = {item['code'] for item in report['context_flags']}
    blockers.extend(sorted(blocking_flags & present))
    blockers = list(dict.fromkeys(blockers))
    return {
        'status': 'READY_FOR_USER_REVIEW' if not blockers else 'NOT_READY',
        'blockers': blockers,
        'author_contact_authorized': False,
        'requires_user_decision': True,
        'meaning': ('All machine-checkable MVP gates passed; source-to-formalization semantics remain an '
                    'agent/user responsibility.' if not blockers else
                    'Resolve the listed blockers before treating this as an author-contact candidate.'),
    }


def html_report(report: dict[str, Any], readiness: dict[str, Any]) -> str:
    status = escape(report['decision'])
    flags = ''.join(f"<li><code>{escape(x['code'])}</code>: {escape(x['detail'])}</li>"
                    for x in report['context_flags']) or '<li>None</li>'
    blockers = ''.join(f'<li><code>{escape(x)}</code></li>' for x in readiness['blockers']) or '<li>None</li>'
    proof = escape(json.dumps(report['formalization_result'], indent=2, sort_keys=True))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ResearchWitness — {escape(report['case_id'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:960px;margin:3rem auto;padding:0 1rem;line-height:1.5}}
code,pre{{font-family:ui-monospace,monospace}} pre{{overflow:auto;padding:1rem;background:#f4f4f4;border-radius:.5rem}}
.badge{{display:inline-block;padding:.25rem .5rem;border:1px solid #777;border-radius:999px}} table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:.45rem;text-align:left}}</style></head><body>
<h1>ResearchWitness evidence report</h1>
<p class="badge">{status}</p>
<table><tr><th>Case</th><td>{escape(report['case_id'])}</td></tr>
<tr><th>Scope</th><td>{escape(report['scope'])}</td></tr>
<tr><th>Source capture</th><td>{escape(report['source_capture_status'])}</td></tr>
<tr><th>Correction status</th><td>{escape(report['correction_status'])}</td></tr>
<tr><th>Contact readiness</th><td>{escape(readiness['status'])}</td></tr></table>
<h2>Important limitation</h2><p><strong>paper_error_established = false.</strong> The deterministic result applies to the supplied formalization and witness. Source interpretation is not machine-proved.</p>
<h2>Context flags</h2><ul>{flags}</ul>
<h2>Contact blockers</h2><ul>{blockers}</ul>
<h2>Formalization result</h2><pre>{proof}</pre>
<h2>Integrity</h2><p>Subject SHA-256: <code>{escape(report['subject_sha256'])}</code><br>Bundle SHA-256: <code>{escape(report['bundle_sha256'])}</code><br>Core SHA-256: <code>{escape(report['core_sha256'])}</code></p>
</body></html>'''


def contact_draft(case: dict[str, Any], report: dict[str, Any], readiness: dict[str, Any]) -> str:
    if readiness['status'] != 'READY_FOR_USER_REVIEW':
        raise ValueError('Case is not ready for a contact draft: ' + ', '.join(readiness['blockers']))
    return f'''Subject: Possible issue with {case['claim']['id']} — reproducible verification inquiry

Hello,

I am writing about the following claim in {case['source']['identifier']} ({case['source']['version']}):

{case['claim']['statement']}

I found an explicit witness that a deterministic checker reports as contradicting the formalization I reconstructed from the cited claim. The result is intentionally narrow: it does not establish that the paper as a whole is incorrect, and I would appreciate confirmation that I have interpreted the claim and its assumptions correctly.

Scope checked:
{case['claim']['scope']}

ResearchWitness decision: {report['decision']}
Subject SHA-256: {report['subject_sha256']}

I can provide the complete evidence capsule and reproduction instructions. If I have missed a restriction, later correction, or different intended interpretation, I would be grateful to know.

Best regards,
'''
