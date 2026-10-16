"""Source-backed documentation contracts and fixed, offline CLI smoke tests.

Never execute arbitrary Markdown, shell fragments or source-supplied commands.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest
from urllib.parse import unquote, urlsplit

from researchwitness import VERSION
from researchwitness.scaffold import scaffold

ROOT = Path(__file__).resolve().parents[1]
MAINTAINED = (
    'README.md', 'CHANGELOG.md', 'docs/PROJECT_STATUS.md',
    'docs/OSS_QUALITY_FINAL.md', 'docs/OSS_MAINTAINER_REVIEW.md',
    'docs/ARCHITECTURE.md', 'docs/ROADMAP.md', 'docs/RELEASING.md',
    'docs/OFFLINE_RESEARCH_AUDIT.md', 'validation/README.md',
)
COMMANDS = {
    'core': ('python', '-m', 'researchwitness', 'verify',
             'examples/counterexample', '--as-of', '2026-10-04'),
    'jats': ('python', '-m', 'tools.research_audit', 'audit',
             'examples/synthetic-jats/article.xml', '--document-id', 'synthetic-jats',
             '--format', 'jats', '--json-output', 'out/synthetic-jats/audit.json',
             '--markdown-output', 'out/synthetic-jats/audit.md'),
}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def without_fences(text: str) -> str:
    return re.sub(r'^`{3}[^\n]*\n.*?^`{3}[ \t]*$', '', text, flags=re.M | re.S)


def heading_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for heading in re.findall(r'^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$', without_fences(text), re.M):
        slug = ''.join(c for c in heading.lower() if c.isalnum() or c in '_- ').replace(' ', '-')
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(f'{slug}-{count}' if count else slug)
    return anchors


class DocumentationTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, '-m', *args], cwd=ROOT,
                              text=True, capture_output=True, timeout=30, check=False)

    def documented_command(self, name: str) -> tuple[str, ...]:
        pattern = rf'<!-- docs-smoke: {name} -->\s*`{{3}}text\n([^\n]+)\n`{{3}}'
        matches = re.findall(pattern, read('README.md'))
        self.assertEqual(len(matches), 1, f'Missing or duplicate smoke block: {name}')
        self.assertEqual(tuple(shlex.split(matches[0])), COMMANDS[name])
        return COMMANDS[name]  # Execute only the fixed allowlist, not extracted text.

    def test_maintained_internal_links_and_heading_fragments(self):
        for relative in MAINTAINED:
            source = ROOT / relative
            for target in re.findall(r'\]\(([^)\s]+)\)', without_fences(read(relative))):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc:
                    continue
                with self.subTest(source=relative, target=target):
                    path = (source.parent / unquote(parsed.path)).resolve() if parsed.path else source
                    self.assertTrue(path.is_relative_to(ROOT))
                    self.assertTrue(path.exists(), f'Broken link: {target}')
                    if parsed.fragment:
                        self.assertTrue(path.is_file())
                        self.assertIn(unquote(parsed.fragment), heading_anchors(path.read_text(encoding='utf-8')))

    def test_version_integration_record_and_historical_provenance(self):
        project = tomllib.loads(read('pyproject.toml'))['project']
        cp = json.loads(read('validation/OSS_QUALITY_CHECKPOINT.json'))
        self.assertEqual(project['version'], VERSION)
        self.assertEqual(cp['version'], VERSION)
        self.assertEqual(cp['release_state'], 'UNRELEASED')
        self.assertEqual(cp['branch'], 'main')
        self.assertIn(f'**On main:** `{VERSION}`', read('README.md'))
        self.assertIn(f'**Version:** `{VERSION}`', read('docs/PROJECT_STATUS.md'))
        self.assertIn(f'## {VERSION} — on main — UNRELEASED', read('CHANGELOG.md'))
        self.assertIn(f'## Main — {VERSION} (UNRELEASED)', read('docs/ROADMAP.md'))
        pr = cp['pull_request']
        self.assertEqual((pr['number'], pr['state'], pr['draft'], pr['merged']),
                         (13, 'closed', False, True))
        self.assertEqual(pr['merge_commit'], cp['integration_baseline']['head'])
        self.assertEqual(pr['qualified_tree'], cp['integration_baseline']['tree'])
        for path in ('docs/PROJECT_STATUS.md', 'docs/OSS_QUALITY_FINAL.md', 'docs/OSS_MAINTAINER_REVIEW.md'):
            text = read(path)
            for key in ('merge_commit', 'qualified_head', 'qualified_tree'):
                self.assertIn(pr[key], text)
            self.assertIn('UNRELEASED', text)
            self.assertNotRegex(text, r'PR (?:\[#13\]\([^)]*\)|#13) remains draft and unmerged')
        historical = cp['historical_pre_merge_record']
        data = (ROOT / historical['path']).read_bytes()
        self.assertEqual(sha256(data).hexdigest(), historical['sha256'])
        self.assertFalse(json.loads(data)['pull_request']['merged'])
        self.assertFalse(cp['quality_acceptance']['independent_human_review'])
        self.assertFalse(cp['boundaries']['scientific_wave_3_run'])
        self.assertFalse(cp['boundaries']['release_published'])

    def test_setup_and_release_instructions_match_declared_requirements(self):
        backend = tomllib.loads(read('pyproject.toml'))['build-system']['requires']
        for path in ('README.md', 'docs/RELEASING.md'):
            text = read(path)
            for requirement in backend:
                self.assertIn(f"python -m pip install '{requirement}'", text)
            self.assertIn('Git on PATH', text)
            self.assertIn('--no-build-isolation', text)
            self.assertIn('--fail-under=90', text)
        for path in ('README.md', 'docs/OFFLINE_RESEARCH_AUDIT.md'):
            text = read(path).replace('**', '')
            self.assertIn('repository root', text)
            self.assertIn("python -m pip install -e '.[dev]'", text)
            self.assertIn('jsonschema', text)
        release = read('docs/RELEASING.md')
        self.assertIn('from tools.make_release import write_checksums; write_checksums()', release)
        self.assertIn('git add -- CHECKSUMS.sha256', release)
        self.assertIn('python -m ruff check .', release)
        self.assertIn('Dependency evidence', release)
        self.assertIn('Analyze Python', release)

    def test_documented_core_example_and_no_refutation_exit_semantics(self):
        command = self.documented_command('core')
        result = self.run_cli(*command[2:])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['decision'], 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED')
        self.assertFalse(report['paper_error_established'])
        self.assertEqual(report['external_actions'], 'OUT_OF_SCOPE')
        self.assertFalse(report['contact_readiness']['author_contact_authorized'])
        result = self.run_cli('researchwitness', 'verify', 'examples/no-finding', '--as-of', '2026-10-04')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['decision'], 'NO_REFUTATION_AT_WITNESS')
        self.assertFalse(report['paper_error_established'])
        self.assertEqual(report['contact_readiness']['status'], 'NOT_READY')

    def test_repeated_utf8_quote_uses_byte_offset_not_character_index(self):
        with tempfile.TemporaryDirectory() as directory:
            intake = scaffold('finite_map_fixed_point', Path(directory) / 'input') / 'audit.json'
            doc = json.loads(intake.read_text(encoding='utf-8'))
            quote = doc['claim']['quote']
            source = f'é prefix\n{quote}\n{quote}\n'
            (intake.parent / doc['source']['text_file']).write_bytes(source.encode('utf-8'))
            doc['claim']['quote_offset'] = source.encode('utf-8').rfind(quote.encode('utf-8'))
            intake.write_text(json.dumps(doc), encoding='utf-8')
            result = self.run_cli('researchwitness', 'validate-intake', str(intake))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['valid'])
            doc['claim']['quote_offset'] = source.rfind(quote)
            intake.write_text(json.dumps(doc), encoding='utf-8')
            result = self.run_cli('researchwitness', 'validate-intake', str(intake))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)['decision'], 'INVALID')

    def test_documented_jats_results_provenance_replay_and_missing_input(self):
        command = self.documented_command('jats')
        self.assertIn(' '.join(command), read('docs/OFFLINE_RESEARCH_AUDIT.md'))
        data = (ROOT / command[4]).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = []
            for name in ('one', 'two', 'one'):
                args = list(command[2:])
                jp, mp = root / f'{name}.json', root / f'{name}.md'
                args[args.index('--json-output') + 1] = str(jp)
                args[args.index('--markdown-output') + 1] = str(mp)
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append((jp.read_bytes(), mp.read_bytes()))
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], outputs[2])
            report = json.loads(outputs[0][0])
            self.assertEqual(report['schema_version'], 'research-audit.v1')
            self.assertEqual(report['processing']['status'], 'completed')
            self.assertEqual(report['processing']['tables_inspected'], 2)
            self.assertEqual(report['processing']['relationships_detected'], 3)
            self.assertEqual(report['summary'], {'arithmetic_matches': 1, 'mismatch_candidates': 1,
                                                'abstentions': 1, 'conditional_mismatches': 0})
            self.assertEqual(report['document']['source_sha256'], sha256(data).hexdigest())
            self.assertEqual(report['document']['provenance_status'], 'unverified_local')
            self.assertFalse(report['document']['provenance_authenticated_by_tool'])
            for relative, expected in report['detector_files'].items():
                self.assertEqual(sha256((ROOT / relative).read_bytes()).hexdigest(), expected)
            self.assertEqual([f['state'] for f in report['findings']],
                             ['arithmetic_match', 'arithmetic_mismatch_candidate', 'extracted_evidence'])
            for finding in report['findings']:
                self.assertEqual(finding['review_state'], 'unreviewed')
                self.assertEqual(finding['scientific_error_status'], 'not_established')
                rel = finding['relationship']
                evidence = rel['evidence']
                cell = data[evidence['byte_start']:evidence['byte_end']]
                token = f'{rel["numerator"]} ({rel["reported_percent"]})'.encode()
                self.assertEqual(cell, b'<td>' + token + b'</td>')
            for finding in report['findings'][:2]:
                rel = finding['relationship']
                self.assertEqual((rel['numerator'], rel['denominator']), (4, 50))
                self.assertEqual(rel['contract_expected_percent'], '8.00')
            self.assertIsNone(report['findings'][2]['relationship']['denominator'])
            markdown = outputs[0][1].decode('utf-8')
            self.assertIn('Matches: 1; mismatch candidates: 1; abstentions: 1;', markdown)
            self.assertIn('calculation withheld', markdown)
            self.assertIn('scientific error status is not established', markdown)
            self.assertNotIn(b'\r\n', outputs[0][0])
            self.assertNotIn(b'\r\n', outputs[0][1])
            args = list(command[2:])
            args[2] = str(root / 'missing.xml')
            jp, mp = root / 'missing.json', root / 'missing.md'
            args[args.index('--json-output') + 1] = str(jp)
            args[args.index('--markdown-output') + 1] = str(mp)
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Research audit failed:', result.stderr)
            self.assertFalse(jp.exists())
            self.assertFalse(mp.exists())


if __name__ == '__main__':
    unittest.main()
