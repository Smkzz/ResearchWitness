import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.pdf_sandbox_image import build


class PDFSandboxImageTests(unittest.TestCase):
    def lock(self):
        return {
            'builder': build.BUILDER, 'snapshot': build.SNAPSHOT, 'suite': 'trixie',
            'architecture': 'amd64',
            'source': f'http://snapshot.debian.org/archive/debian/{build.SNAPSHOT}/',
            'inrelease_sha256': 'a' * 64, 'signing_fingerprints': ['A' * 40],
            'packages': [{'name': 'poppler-utils', 'version': '1:25.03.0-5+deb13u4',
                          'arch': 'amd64', 'filename': 'pool/main/p/poppler/poppler-utils.deb',
                          'sha256': 'b' * 64}],
        }

    def test_valid_lock(self):
        build.validate_lock(self.lock())

    def test_empty_packages_and_missing_signatures_fail(self):
        for key in ('packages', 'signing_fingerprints'):
            lock = self.lock()
            lock[key] = []
            with self.subTest(key=key), self.assertRaises(ValueError):
                build.validate_lock(lock)

    def test_wrong_pins_and_missing_hash_fail(self):
        for key in ('builder', 'snapshot', 'suite', 'architecture', 'source', 'inrelease_sha256'):
            lock = self.lock()
            lock[key] = 'invalid'
            with self.subTest(key=key), self.assertRaises(ValueError):
                build.validate_lock(lock)

    def test_unsafe_package_metadata_fails(self):
        for key, value in [('name', '-x'), ('version', '1\nother'), ('arch', 'arm64'),
                           ('filename', 'pool/main/../bad.deb'), ('sha256', 'not-a-hash')]:
            lock = self.lock()
            lock['packages'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build.validate_lock(lock)
        lock = self.lock()
        lock['packages'].append(copy.deepcopy(lock['packages'][0]))
        with self.assertRaises(ValueError):
            build.validate_lock(lock)

    def test_import_is_local_without_config_changes(self):
        image_id = 'sha256:' + 'c' * 64
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            result = subprocess.CompletedProcess([], 0, (image_id + '\n').encode())
            with patch.object(build.subprocess, 'run', return_value=result) as run:
                build.image(work, work)
            self.assertEqual(run.call_args.args[0], ['docker', 'import', str(work / 'rootfs.tar')])
            self.assertEqual((work / 'image-id.txt').read_text().strip(), image_id)
            self.assertIn('EXIT CODE: 0', (work / f'{work.name}-import.log').read_text())

    def test_import_failure_or_invalid_id_never_writes_pin(self):
        for code, output, error in [(1, b'failed', SystemExit), (0, b'', ValueError)]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                result = subprocess.CompletedProcess([], code, output)
                with patch.object(build.subprocess, 'run', return_value=result), self.assertRaises(error):
                    build.image(work, work)
                self.assertFalse((work / 'image-id.txt').exists())

    def test_invalid_lock_stops_before_builder_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            lock = self.lock()
            lock['packages'] = []
            (work / 'packages.lock.json').write_text(json.dumps(lock))
            with patch.object(build, 'run_script') as run, self.assertRaises(ValueError):
                build.build(work, work)
            run.assert_not_called()

    def test_builder_error_is_logged_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            result = subprocess.CompletedProcess([], 100, b'signature failed\r\n')
            with patch.object(build.subprocess, 'run', return_value=result), self.assertRaises(SystemExit):
                build.run_script('prepare.sh', work, work / 'run.log')
            self.assertIn('signature failed\n\nEXIT CODE: 100\n', (work / 'run.log').read_text())


if __name__ == '__main__':
    unittest.main()
