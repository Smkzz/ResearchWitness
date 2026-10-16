"""In-process coverage for the public command-line dispatch paths."""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from researchwitness.__main__ import main
from researchwitness.scaffold import scaffold
from researchwitness.strict import digest, loads


ROOT = Path(__file__).resolve().parents[1]


class CliDispatchTests(unittest.TestCase):
    def invoke(self, *args: str) -> tuple[int, str, str]:
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                result = main(list(args))
            except SystemExit as exc:
                result = exc.code
        return int(result), stdout.getvalue(), stderr.getvalue()

    def test_version_capabilities_and_embedded_schemas(self):
        code, output, _ = self.invoke('--version')
        self.assertEqual(code, 0)
        self.assertTrue(output.startswith('researchwitness '))

        code, output, _ = self.invoke('capabilities', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(output)['checkers']), 10)

        for name, expected_title in (
            ('case', 'ResearchWitness private evidence capsule 1.0'),
            ('intake', 'ResearchWitness agent intake 0.1'),
        ):
            with self.subTest(schema=name):
                code, output, _ = self.invoke('schema', name)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output)['title'], expected_title)

    def test_scaffold_validate_prepare_and_error_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_dir = root / 'scaffold'
            code, output, _ = self.invoke(
                'scaffold', 'finite_map_fixed_point', '--output', str(scaffold_dir)
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)['source_capture_status'], 'synthetic')
            self.assertTrue((scaffold_dir / 'README.txt').is_file())

            intake = scaffold_dir / 'audit.json'
            code, output, _ = self.invoke('validate-intake', str(intake))
            validated = json.loads(output)
            self.assertEqual(code, 0)
            self.assertTrue(validated['valid'])
            self.assertEqual(validated['source_provenance'], 'NOT_AUTHENTICATED')

            bundle = root / 'bundle'
            code, output, _ = self.invoke('prepare', str(intake), '--output', str(bundle))
            self.assertEqual(code, 0)
            self.assertTrue((bundle / 'case.json').is_file())

            code, _, error = self.invoke(
                'prepare', str(intake), '--output', str(bundle)
            )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(error)['decision'], 'INVALID')

            code, _, error = self.invoke(
                'scaffold', 'finite_map_fixed_point', '--output', str(scaffold_dir)
            )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(error)['decision'], 'INVALID')

    def test_audit_creates_bundle_and_html_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intake = scaffold('finite_map_fixed_point', root / 'input') / 'audit.json'
            bundle, html = root / 'bundle', root / 'report.html'
            code, output, _ = self.invoke(
                'audit', str(intake), '--output', str(bundle), '--html', str(html),
                '--as-of', '2026-10-04',
            )
            result = json.loads(output)
            self.assertEqual(code, 0)
            self.assertEqual(result['report']['decision'], 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED')
            self.assertEqual(result['contact_readiness']['status'], 'NOT_READY')
            self.assertTrue(html.is_file())
            self.assertIn('paper_error_established = false', html.read_text(encoding='utf-8'))

    def test_bundle_commands_verify_subject_report_and_deterministic_pack(self):
        bundle = ROOT / 'examples' / 'counterexample'
        code, output, _ = self.invoke('verify', str(bundle), '--as-of', '2026-10-04')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['decision'], 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED')

        code, output, _ = self.invoke('subject', str(bundle), '--as-of', '2026-10-04')
        self.assertEqual(code, 0)
        self.assertEqual(len(output.strip()), 64)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'report.html'
            code, output, _ = self.invoke(
                'report', str(bundle), '--as-of', '2026-10-04', '--output', str(report)
            )
            self.assertEqual(code, 0)
            self.assertTrue(report.is_file())
            self.assertEqual(json.loads(output)['decision'], 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED')

            archives = [root / 'one.zip', root / 'two.zip']
            for archive in archives:
                code, _, _ = self.invoke(
                    'pack', str(bundle), '--as-of', '2026-10-04', '--output', str(archive)
                )
                self.assertEqual(code, 0)
                with zipfile.ZipFile(archive) as zipped:
                    self.assertIn('report.json', zipped.namelist())
                    self.assertIn('contact-readiness.json', zipped.namelist())
                    self.assertEqual(
                        json.loads(zipped.read('report.json'))['paper_error_established'], False
                    )
            self.assertEqual(sha256(archives[0].read_bytes()).digest(),
                             sha256(archives[1].read_bytes()).digest())

    def test_contact_draft_is_user_review_only_and_blocked_cases_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intake = scaffold('finite_map_fixed_point', root / 'input') / 'audit.json'
            payload = json.loads(intake.read_text(encoding='utf-8'))
            payload['source']['capture_status'] = 'captured'
            payload['source']['correction_check']['status'] = 'none_found'
            payload['source']['correction_check']['checked_on'] = '2026-10-04'
            payload['unresolved_objections'] = []
            intake.write_text(json.dumps(payload), encoding='utf-8')
            bundle = root / 'prepared'
            code, _, error = self.invoke('prepare', str(intake), '--output', str(bundle))
            self.assertEqual(code, 0, error)

            draft = root / 'draft.md'
            code, output, _ = self.invoke(
                'contact-draft', str(bundle), '--as-of', '2026-10-04', '--output', str(draft)
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)['status'], 'USER_REVIEW_REQUIRED')
            self.assertTrue(draft.is_file())
            self.assertIn('does not establish that the paper as a whole is incorrect',
                          draft.read_text(encoding='utf-8'))

            blocked = root / 'blocked'
            scaffold('finite_map_fixed_point', blocked)
            code, _, error = self.invoke(
                'contact-draft', str(blocked), '--as-of', '2026-10-04', '--output', str(root / 'no.md')
            )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(error)['decision'], 'INVALID')

    def test_timeline_cli_checks_optional_external_digest(self):
        bundle = ROOT / 'examples' / 'correction-history'
        timeline_path = bundle / 'timeline.json'
        timeline = loads(timeline_path.read_bytes())
        expected = digest(timeline)
        code, output, _ = self.invoke(
            'timeline', str(bundle), '--timeline', str(timeline_path),
            '--as-of', '2026-10-04', '--expected-timeline-sha256', expected,
        )
        result = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(result['event_count'], 4)
        self.assertTrue(result['externally_pinned'])
        self.assertFalse(result['correction_verified'])

    def test_invalid_bundle_reports_json_error_and_parser_error_is_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, error = self.invoke('verify', str(Path(directory) / 'missing'))
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(error)['decision'], 'INVALID')
        code, _, error = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn('usage:', error)


if __name__ == '__main__':
    unittest.main()
