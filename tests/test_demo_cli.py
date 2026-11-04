"""Offline first-run workflow is a real installed-package path, not paper proof."""
from __future__ import annotations

import json
from datetime import date
import subprocess
import sys

import pytest

from researchwitness import VERSION
from researchwitness.__main__ import main
from researchwitness.capsule import evaluate


def test_demo_produces_replayable_synthetic_evidence(tmp_path, capsys):
    root = tmp_path / 'first-run'
    assert main(['demo', '--output', str(root)]) == 0
    shown = json.loads(capsys.readouterr().out)
    stored = json.loads((root / 'demo-result.json').read_text(encoding='utf-8'))
    assert shown == stored
    assert shown['version'] == VERSION
    assert shown['status'] == 'synthetic_demo_complete'
    assert shown['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert shown['contact_readiness'] == 'NOT_READY'
    assert shown['source_type'] == 'SYNTHETIC_FIXTURE_NOT_PUBLICATION'
    assert shown['external_actions'] == 'OUT_OF_SCOPE'
    assert shown['paper_error_established'] is False
    assert shown['scientific_accuracy_established'] is False
    assert shown['author_contact_authorized'] is False
    assert (root / 'intake' / 'source.txt').is_file()
    report = evaluate(root / 'bundle', date(2026, 10, 4))
    assert report['bundle_sha256'] == shown['bundle_sha256']
    assert report['subject_sha256'] == shown['subject_sha256']
    assert report['paper_error_established'] is False


def test_demo_never_overwrites_existing_data(tmp_path, capsys):
    root = tmp_path / 'existing'
    root.mkdir()
    secret = root / 'do-not-touch.txt'
    secret.write_bytes(b'owned file')
    assert main(['demo', '--output', str(root)]) == 2
    assert secret.read_bytes() == b'owned file'
    assert not (root / 'demo-result.json').exists()
    assert json.loads(capsys.readouterr().err)['decision'] == 'INVALID'


@pytest.mark.parametrize('kind', ['finite_pmf_bound', 'finite_map_fixed_point'])
def test_demo_works_outside_checkout_and_optimized_mode(tmp_path, kind):
    outputs = []
    for optimized in (False, True):
        root = tmp_path / (kind + ('-optimized' if optimized else '-normal'))
        cmd = [sys.executable] + (['-O'] if optimized else [])
        cmd += ['-m', 'researchwitness', 'demo', '--kind', kind,
                '--output', str(root), '--as-of', '2026-10-04']
        proc = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True,
                              timeout=20)
        assert proc.returncode == 0, proc.stderr
        status = json.loads(proc.stdout)
        assert status['source_type'] == 'SYNTHETIC_FIXTURE_NOT_PUBLICATION'
        assert status['paper_error_established'] is False
        assert status['external_actions'] == 'OUT_OF_SCOPE'
        outputs.append((status['decision'], status['bundle_sha256'],
                        status['subject_sha256']))
    assert outputs[0] == outputs[1]


def test_demo_rejects_unknown_checker_kind(tmp_path):
    command = [sys.executable, '-m', 'researchwitness', 'demo',
               '--kind', 'unbounded_ai_paper_verification',
               '--output', str(tmp_path / 'unknown')]
    proc = subprocess.run(command, cwd=tmp_path, capture_output=True,
                          text=True, timeout=20)
    assert proc.returncode == 2
    assert not (tmp_path / 'unknown').exists()
