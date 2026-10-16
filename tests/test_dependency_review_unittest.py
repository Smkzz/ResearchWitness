import importlib.util
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / 'tools' / 'dependency_review.py'
SPEC = importlib.util.spec_from_file_location('dependency_review', MODULE_PATH)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class DependencyReviewTests(unittest.TestCase):
    def test_license_log_preserves_non_utf8_bytes(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[1]) as temporary:
            root = Path(temporary)
            license_path = root / 'licenses' / 'example.txt'
            license_path.parent.mkdir()
            license_path.write_bytes(b'copyright\xff\x1b\n')
            output = io.StringIO()
            with redirect_stdout(output):
                review.print_license_evidence(root)
            line = output.getvalue().splitlines()
            self.assertEqual(len(line), 1)
            record = json.loads(line[0].removeprefix('RW_LICENSE_FILE '))
            self.assertEqual(base64.b64decode(record['content_base64']), license_path.read_bytes())

    def test_license_paths_links_and_size_are_rejected_before_query(self):
        class Metadata(dict):
            def get_all(self, _key, default):
                return default

        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[1]) as temporary:
            root = Path(temporary)

            class Dist:
                metadata = Metadata(Name='example')
                version = '1'
                requires = []
                files = []

                def locate_file(self, entry):
                    return root / entry

            dist = Dist()
            dist.files = [Path('../LICENSE')]
            with patch.object(review, 'query') as query:
                with self.assertRaisesRegex(ValueError, 'escapes'):
                    review.capture_distribution(dist, root / 'out')
                query.assert_not_called()
            oversized = root / 'LICENSE'
            with oversized.open('wb') as stream:
                stream.truncate(4 * 1024 * 1024 + 1)
            dist.files = [Path('LICENSE')]
            with patch.object(review, 'query') as query:
                with self.assertRaisesRegex(ValueError, 'file bound'):
                    review.capture_distribution(dist, root / 'out')
                query.assert_not_called()
            linked = root / 'LICENSE.link'
            try:
                os.link(oversized, linked)
            except OSError:
                return  # Link creation can be unavailable; other cases remain tested.
            dist.files = [Path('LICENSE.link')]
            with patch.object(review, 'query') as query:
                with self.assertRaisesRegex(ValueError, 'unlinked'):
                    review.capture_distribution(dist, root / 'out')
                query.assert_not_called()

    def test_distribution_license_bytes_and_advisories_are_retained(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[1]) as temporary:
            root = Path(temporary)
            license_path = root / 'LICENSE'
            license_path.write_bytes(b'MIT license evidence\n')

            class Dist:
                metadata = {'Name': 'example-package'}
                version = '1.2.3'
                requires = ['example-child>=1']
                files = [Path('LICENSE')]

                def locate_file(self, _entry):
                    return root if _entry == '' else license_path

            class Metadata(dict):
                def get_all(self, _key, default):
                    return default

            dist = Dist()
            dist.metadata = Metadata(dist.metadata)
            with patch.object(review, 'query', side_effect=[{'vulnerabilities': [{'id': 'EXAMPLE-1'}], 'urls': []}, {}]) as query:
                result = review.capture_distribution(dist, root / 'out')
            self.assertEqual(result['pypi_advisories'], [{'id': 'EXAMPLE-1'}])
            self.assertEqual(result['osv_advisories'], [])
            evidence = root / 'out' / result['license_files'][0]['evidence']
            self.assertEqual(evidence.read_bytes(), license_path.read_bytes())
            self.assertEqual(query.call_args_list[1].args[1]['version'], '1.2.3')

    def test_advisory_query_rejects_non_object(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, limit):
                return json.dumps([]).encode()

        with patch.object(review, 'urlopen', return_value=Response()):
            with self.assertRaisesRegex(ValueError, 'invalid advisory response'):
                review.query('https://pypi.org/pypi/example/1/json')

    def test_osv_pagination_and_error_payloads(self):
        with patch.object(review, 'query', side_effect=[{'next_page_token': 'p2'}, {'vulns': [{'id': 'EXAMPLE'}]}]):
            self.assertEqual(review.osv_advisories('example', '1'), [{'id': 'EXAMPLE'}])
        for response in ({'error': 'provider failed'}, {'vulns': None}, {'vulns': ['bad']}, {'vulns': [None]}, {'next_page_token': 1}):
            with self.subTest(response=response), patch.object(review, 'query', return_value=response):
                with self.assertRaises(ValueError):
                    review.osv_advisories('example', '1')

    def test_distribution_identity_cannot_escape_output(self):
        class Dist:
            metadata = {'Name': '../outside'}
            version = '1'

        with self.assertRaisesRegex(ValueError, 'nonportable distribution identity'):
            review.capture_distribution(Dist(), Path('.'))


if __name__ == '__main__':
    unittest.main()
